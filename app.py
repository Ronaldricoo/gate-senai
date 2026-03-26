import sqlite3
import os  # <--- ESSENCIAL: Adicione esta linha!
from flask import Flask, render_template, request, redirect, url_for, jsonify, session

# Configuração do caminho do banco de dados para o Render
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'database.db')

app = Flask(__name__)
app.secret_key = os.urandom(24) # Gera uma chave segura para o servidor online

DATABASE = 'database.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Criar as tabelas no início
def init_db():
    with get_db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS usuarios 
            (id TEXT PRIMARY KEY, senha TEXT, role TEXT, nome TEXT, tag TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS solicitacoes 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, professor_tag TEXT, professor_nome TEXT, lab TEXT, data TEXT, periodo TEXT, status TEXT)''')

        # Cria o admin padrão se não existir
        admin = db.execute("SELECT * FROM usuarios WHERE id = 'admin'").fetchone()
        if not admin:
            db.execute("INSERT INTO usuarios VALUES ('admin', '123', 'admin', 'Administrador', '000000')")
        db.commit()


init_db()


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
            if user and user['senha'] == senha:
                session.update(
                    {'usuario_id': user['id'], 'nome': user['nome'], 'role': user['role'], 'tag': user['tag']})
                return redirect(url_for('tela_aprovar' if user['role'] == 'admin' else 'tela_solicitar'))
        return "Erro: Credenciais inválidas."
    return render_template('login.html')


@app.route('/usuarios')
def gerenciar_usuarios():
    if session.get('role') != 'admin': return "Negado", 403
    with get_db() as db:
        usuarios = db.execute("SELECT * FROM usuarios").fetchall()
    return render_template('usuarios.html', usuarios=usuarios)


@app.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    if session.get('role') != 'admin': return "Negado", 403
    with get_db() as db:
        db.execute("INSERT INTO usuarios (id, nome, senha, tag, role) VALUES (?, ?, ?, ?, 'professor')",
                   (request.form.get('user_id'), request.form.get('nome'), request.form.get('senha'),
                    request.form.get('tag').upper()))
        db.commit()
    return redirect(url_for('gerenciar_usuarios'))


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
            (session.get('tag'), session.get('nome'), request.form.get('lab'), request.form.get('data'),
             request.form.get('periodo')))
        db.commit()
    return redirect(url_for('tela_solicitar'))


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


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/rfid', methods=['POST'])
def verificar_acesso():
    dados = request.get_json()
    tag_id = dados.get('tag', '').upper()
    with get_db() as db:
        # Busca se há agendamento aprovado para hoje (simplificado)
        agendamento = db.execute(
            "SELECT professor_nome FROM solicitacoes WHERE professor_tag = ? AND status = 'Aprovado'",
            (tag_id,)).fetchone()
        if agendamento:
            return jsonify({"access": True, "name": agendamento['professor_nome']}), 200
    return jsonify({"access": False, "name": "Negado"}), 401


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
