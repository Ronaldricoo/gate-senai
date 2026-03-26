import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session

# 1. CONFIGURAÇÃO DE CAMINHOS PARA O RENDER
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'database.db')

app = Flask(__name__)
# Usamos uma chave fixa para evitar deslogar toda vez que o Render reiniciar
app.secret_key = 'chave_mestra_senai_9168' 

# 2. FUNÇÕES DO BANCO DE DADOS
def get_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    with get_db() as db:
        # Tabela de Usuários
        db.execute('''CREATE TABLE IF NOT EXISTS usuarios 
            (id TEXT PRIMARY KEY, senha TEXT, role TEXT, nome TEXT, tag TEXT)''')
        
        # Tabela de Solicitações
        db.execute('''CREATE TABLE IF NOT EXISTS solicitacoes 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, professor_tag TEXT, professor_nome TEXT, lab TEXT, data TEXT, periodo TEXT, status TEXT)''')
        
        # Garante que o admin SEMPRE exista (login: admin / senha: 123)
        admin = db.execute("SELECT * FROM usuarios WHERE id = 'admin'").fetchone()
        if not admin:
            db.execute("INSERT INTO usuarios VALUES ('admin', '123', 'admin', 'Administrador', '000000')")
        db.commit()

# Inicializa o banco automaticamente ao subir o app
with app.app_context():
    init_db()

# 3. ROTAS DE ACESSO E LOGIN
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha = request.form.get('senha')
        with get_db() as db:
            user = db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario,)).fetchone()
            
            # Verificação de senha convertendo para string para evitar erros
            if user and str(user['senha']) == str(senha):
                session.clear()
                session['usuario_id'] = user['id']
                session['nome'] = user['nome']
                session['role'] = user['role']
                session['tag'] = user['tag']
                
                if user['role'] == 'admin':
                    return redirect(url_for('tela_aprovar'))
                return redirect(url_for('tela_solicitar'))
        
        return "Erro: Credenciais inválidas. <a href='/login'>Tentar novamente</a>"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# 4. ÁREA DO ADMINISTRADOR
@app.route('/usuarios')
def gerenciar_usuarios():
    # Verificação rigorosa de segurança
    if session.get('role') != 'admin':
        return f"Acesso Negado! Logue como admin. Seu nível: {session.get('role')}", 403
        
    with get_db() as db:
        usuarios = db.execute("SELECT * FROM usuarios").fetchall()
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    if session.get('role') != 'admin': return "Negado", 403
    
    uid = request.form.get('user_id')
    nome = request.form.get('nome')
    pw = request.form.get('senha')
    tg = request.form.get('tag', '').upper()

    with get_db() as db:
        try:
            db.execute("INSERT INTO usuarios (id, nome, senha, tag, role) VALUES (?, ?, ?, ?, 'professor')",
                       (uid, nome, pw, tg))
            db.commit()
        except sqlite3.IntegrityError:
            return "Erro: Este login já existe. <a href='/usuarios'>Voltar</a>"
            
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/excluir_usuario/<user_id>')
def excluir_usuario(user_id):
    if session.get('role') != 'admin': return "Negado", 403
    if user_id != 'admin':
        with get_db() as db:
            db.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
            db.commit()
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/admin')
def tela_aprovar():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    with get_db() as db:
        solics = db.execute("SELECT * FROM solicitacoes").fetchall()
    return render_template('aprovar.html', solicitacoes=solics)

@app.route('/decisao/<int:solic_id>/<string:status>')
def decidir(solic_id, status):
    if session.get('role') == 'admin':
        with get_db() as db:
            db.execute("UPDATE solicitacoes SET status = ? WHERE id = ?", (status, solic_id))
            db.commit()
    return redirect(url_for('tela_aprovar'))

# 5. ÁREA DO PROFESSOR E API
@app.route('/solicitar')
def tela_solicitar():
    if not session.get('usuario_id'): return redirect(url_for('login'))
    return render_template('solicitar.html', labs=["Informática", "Redes", "Robótica"])

@app.route('/enviar_solicitacao', methods=['POST'])
def enviar_solicitacao():
    if not session.get('usuario_id'): return redirect(url_for('login'))
    with get_db() as db:
        db.execute(
            "INSERT INTO solicitacoes (professor_tag, professor_nome, lab, data, periodo, status) VALUES (?, ?, ?, ?, ?, 'Pendente')",
            (session.get('tag'), session.get('nome'), request.form.get('lab'), 
             request.form.get('data'), request.form.get('periodo')))
        db.commit()
    return redirect(url_for('tela_solicitar'))

@app.route('/api/rfid', methods=['POST'])
def verificar_acesso():
    dados = request.get_json()
    tag_id = dados.get('tag', '').upper()
    with get_db() as db:
        # Verifica se há agendamento aprovado para a tag
        agendamento = db.execute(
            "SELECT professor_nome FROM solicitacoes WHERE professor_tag = ? AND status = 'Aprovado'", 
            (tag_id,)).fetchone()
        if agendamento:
            return jsonify({"access": True, "name": agendamento['professor_nome']}), 200
    return jsonify({"access": False, "name": "Negado"}), 401

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
