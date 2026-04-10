import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_mail import Mail, Message
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = 'chave_mestra_senai_9168'

# --- CONFIGURAÇÃO DE E-MAIL ---
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='seu-email@gmail.com', # SEU EMAIL
    MAIL_PASSWORD='xxxx xxxx xxxx xxxx', # SUA SENHA DE APP
    MAIL_DEFAULT_SENDER='seu-email@gmail.com'
)
mail = Mail(app)

# --- MONGODB ---
MONGO_URI = "mongodb+srv://ronald:senai123@gate.cof2msq.mongodb.net/?appName=gate"
client = MongoClient(MONGO_URI)
db = client['gate_senai']

# --- FUNÇÕES AUXILIARES ---
def get_agora_mt():
    return datetime.now(timezone.utc) - timedelta(hours=4)

def determinar_periodo(hora_str):
    if "07:00" <= hora_str <= "12:00": return "Manhã"
    elif "13:00" <= hora_str <= "18:00": return "Tarde"
    elif "18:20" <= hora_str <= "22:30": return "Noite"
    return None

# --- ROTAS DE LOGIN E LOGOUT ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('usuario')
        senha = request.form.get('senha')
        user = db.usuarios.find_one({"id": user_id})
        if user and str(user['senha']) == str(senha):
            session.clear()
            session['usuario_id'] = user['id']
            session['nome'] = user['nome']
            session['role'] = user['role']
            session['tag'] = user['tag']
            return redirect(url_for('tela_aprovar' if user['role'] == 'admin' else 'rota_solicitar'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- GESTÃO DE USUÁRIOS ---

@app.route('/usuarios')
def rota_usuarios():
    if session.get('role') != 'admin': return "Acesso Negado", 403
    users = list(db.usuarios.find())
    return render_template('usuarios.html', usuarios=users)

@app.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    if session.get('role') != 'admin': return "Negado", 403
    db.usuarios.insert_one({
        "id": request.form.get('user_id'),
        "nome": request.form.get('nome'),
        "senha": request.form.get('senha'),
        "tag": request.form.get('tag', '').upper(),
        "email": request.form.get('email'),
        "role": "professor"
    })
    return redirect(url_for('rota_usuarios'))

@app.route('/excluir_usuario/<user_id>')
def excluir_usuario(user_id):
    if session.get('role') == 'admin' and user_id != 'admin':
        db.usuarios.delete_one({"id": user_id})
    return redirect(url_for('rota_usuarios'))

# --- SOLICITAÇÕES (COM TRAVA DE DUPLICIDADE) ---

@app.route('/solicitar')
def rota_solicitar():
    if not session.get('usuario_id'): return redirect(url_for('login'))
    return render_template('solicitar.html', labs=["Informática", "Redes", "Robótica"])

@app.route('/enviar_solicitacao', methods=['POST'])
def enviar_solicitacao():
    if not session.get('usuario_id'): return redirect(url_for('login'))
    
    lab = request.form.get('lab')
    data = request.form.get('data')
    periodo = request.form.get('periodo')

    # BLOQUEIO DE DUPLICIDADE
    existente = db.solicitacoes.find_one({
        "lab": lab, "data": data, "periodo": periodo, "status": "Aprovado"
    })
    if existente:
        return f"<h3>Erro: O {lab} já está reservado para {data} ({periodo}).</h3><a href='/solicitar'>Voltar</a>"

    db.solicitacoes.insert_one({
        "professor_tag": session.get('tag'),
        "professor_nome": session.get('nome'),
        "professor_email": session.get('email'),
        "lab": lab, "data": data, "periodo": periodo, "status": "Pendente"
    })

    # Notifica Admin
    try:
        admin = db.usuarios.find_one({"role": "admin"})
        if admin and admin.get('email'):
            msg = Message("Nova Solicitação - Gate SENAI", recipients=[admin['email']])
            msg.body = f"Nova solicitação de {session['nome']} para o {lab} em {data}."
            mail.send(msg)
    except: pass

    return redirect(url_for('rota_solicitar'))

# --- PAINEL DE APROVAÇÃO (COM FILTROS) ---

@app.route('/aprovar')
def tela_aprovar():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    
    filtro = request.args.get('filtro', 'Pendente')
    hoje = get_agora_mt().strftime('%Y-%m-%d')
    
    if filtro == "Pendentes": query = {"status": "Pendente"}
    elif filtro == "Futuros": query = {"status": "Aprovado", "data": {"$gte": hoje}}
    elif filtro == "Passados": query = {"$or": [{"data": {"$lt": hoje}}, {"status": "Reprovado"}]}
    else: query = {"status": "Pendente"}

    solics = list(db.solicitacoes.find(query))
    return render_template('aprovar.html', solicitacoes=solics, filtro_atual=filtro)

@app.route('/decisao/<solic_id>/<status>')
def decidir(solic_id, status):
    if session.get('role') == 'admin':
        solic = db.solicitacoes.find_one_and_update(
            {"_id": ObjectId(solic_id)}, {"$set": {"status": status}}
        )
        # Notifica Professor
        prof = db.usuarios.find_one({"tag": solic['professor_tag']})
        if prof and prof.get('email'):
            try:
                msg = Message(f"Solicitação {status}", recipients=[prof['email']])
                msg.body = f"Sua reserva para o {solic['lab']} em {solic['data']} foi {status}."
                mail.send(msg)
            except: pass
    return redirect(url_for('tela_aprovar'))

# --- RELATÓRIO DE CARGA HORÁRIA ---

@app.route('/relatorio')
def rota_relatorio():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    
    mes_atual = get_agora_mt().strftime('%Y-%m')
    labs = ["Informática", "Redes", "Robótica"]
    dados_relatorio = []

    for lab in labs:
        # Cada reserva aprovada no mês conta como 5 horas de utilização
        qtd = db.solicitacoes.count_documents({
            "lab": lab, "status": "Aprovado", "data": {"$regex": f"^{mes_atual}"}
        })
        dados_relatorio.append({"lab": lab, "horas": qtd * 5, "reservas": qtd})

    return render_template('relatorio.html', dados=dados_relatorio, mes=mes_atual)

# --- API PARA OS 3 ESP32 (VALIDAÇÃO POR LAB) ---

@app.route('/api/rfid', methods=['POST'])
def verificar_acesso():
    dados = request.get_json()
    tag_id = dados.get('tag', '').upper()
    lab_id = dados.get('lab') # Enviado pelo ESP32 (Ex: "Redes")
    
    usuario = db.usuarios.find_one({"tag": tag_id})
    if not usuario: return jsonify({"access": False, "name": "Inexistente"}), 401

    agora = get_agora_mt()
    hoje = agora.strftime('%Y-%m-%d')
    periodo = determinar_periodo(agora.strftime('%H:%M'))

    if not periodo: return jsonify({"access": False, "name": "Fora de Horario"}), 401

    reserva = db.solicitacoes.find_one({
        "professor_tag": tag_id,
        "lab": lab_id,
        "status": "Aprovado",
        "data": hoje,
        "periodo": periodo
    })

    if reserva:
        return jsonify({"access": True, "name": usuario['nome']}), 200
    return jsonify({"access": False, "name": "Sem Reserva"}), 401

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
