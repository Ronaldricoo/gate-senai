import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'chave_mestra_senai_9168'

# --- CONFIGURAÇÃO DO MONGODB ---
# Usando a sua senha senai123
MONGO_URI = "mongodb+srv://ronald:senai123@gate.cof2msq.mongodb.net/?appName=gate"

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Tenta dar um "ping" no banco para ver se responde
    client.admin.command('ping')
    print(">>> SUCESSO: Conectado ao MongoDB Atlas! <<<")
    db = client['gate_senai']
    
    # Define as coleções APENAS se a conexão funcionar
    usuarios = db['usuarios']
    solicitacoes = db['solicitacoes']

    # Criar admin padrão se não existir
    if not usuarios.find_one({"id": "admin"}):
        usuarios.insert_one({
            "id": "admin",
            "senha": "123",
            "role": "admin",
            "nome": "Administrador",
            "tag": "000000"
        })
except Exception as e:
    print(f">>> ERRO CRÍTICO DE CONEXÃO: {e} <<<")
    db = None

# --- ROTAS DE ACESSO ---
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('usuario')
        senha = request.form.get('senha')
        
        if db is not None:
            user = usuarios.find_one({"id": user_id})
            if user and str(user['senha']) == str(senha):
                session.clear()
                session['usuario_id'] = user['id']
                session['nome'] = user['nome']
                session['role'] = user['role']
                session['tag'] = user['tag']
                
                if user['role'] == 'admin':
                    return redirect(url_for('tela_aprovar'))
                return redirect(url_for('tela_solicitar'))
        
        return "Erro: Falha no login ou banco inacessível. <a href='/login'>Voltar</a>"
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ÁREA DO ADMINISTRADOR ---
@app.route('/usuarios')
def gerenciar_usuarios():
    if session.get('role') != 'admin':
        return "Acesso Negado", 403
    
    lista_users = list(usuarios.find())
    return render_template('usuarios.html', usuarios=lista_users)

@app.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    if session.get('role') != 'admin': return "Negado", 403
    
    novo_user = {
        "id": request.form.get('user_id'),
        "nome": request.form.get('nome'),
        "senha": request.form.get('senha'),
        "tag": request.form.get('tag', '').upper(),
        "role": "professor"
    }
    
    if not usuarios.find_one({"id": novo_user['id']}):
        usuarios.insert_one(novo_user)
        
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/excluir_usuario/<user_id>')
def excluir_usuario(user_id):
    if session.get('role') != 'admin': return "Negado", 403
    if user_id != 'admin':
        usuarios.delete_one({"id": user_id})
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/admin')
def tela_aprovar():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    lista_solics = list(solicitacoes.find())
    return render_template('aprovar.html', solicitacoes=lista_solics)

@app.route('/decisao/<solic_id>/<status>')
def decidir(solic_id, status):
    if session.get('role') == 'admin':
        solicitacoes.update_one(
            {"_id": ObjectId(solic_id)}, 
            {"$set": {"status": status}}
        )
    return redirect(url_for('tela_aprovar'))

# --- ÁREA DO PROFESSOR ---
@app.route('/solicitar')
def tela_solicitar():
    if not session.get('usuario_id'): return redirect(url_for('login'))
    return render_template('solicitar.html', labs=["Informática", "Redes", "Robótica"])

@app.route('/enviar_solicitacao', methods=['POST'])
def enviar_solicitacao():
    if not session.get('usuario_id'): return redirect(url_for('login'))
    
    hora_mt = datetime.utcnow() - timedelta(hours=4)
    
    nova_solic = {
        "professor_tag": session.get('tag'),
        "professor_nome": session.get('nome'),
        "lab": request.form.get('lab'),
        "data": request.form.get('data'),
        "periodo": request.form.get('periodo'),
        "status": "Pendente",
        "criado_em": hora_mt.strftime('%d/%m/%Y %H:%M')
    }
    solicitacoes.insert_one(nova_solic)
    return redirect(url_for('tela_solicitar'))

# --- API PARA O ESP32 ---
@app.route('/api/rfid', methods=['POST'])
def verificar_acesso():
    dados = request.get_json()
    if not dados or 'tag' not in dados:
        return jsonify({"access": False, "name": "Erro"}), 400
        
    tag_id = dados.get('tag', '').upper()
    agendamento = solicitacoes.find_one({
        "professor_tag": tag_id, 
        "status": "Aprovado"
    })
    
    if agendamento:
        return jsonify({
            "access": True, 
            "name": agendamento['professor_nome']
        }), 200
            
    return jsonify({"access": False, "name": "Negado"}), 401

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
