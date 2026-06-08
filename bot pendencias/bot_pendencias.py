#!/usr/bin/env python3
"""
Bot de Pendências Financeiras — CLI
Rastreia divisões de gastos com amigos + integração Google Sheets (PIX).
"""

import sqlite3
import os
import sys
import re
from datetime import datetime
from typing import Optional

# ─── Cores ANSI ──────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
GRAY    = "\033[90m"
BLUE    = "\033[94m"

def cor(texto, c):  return f"{c}{texto}{RESET}"
def titulo(t):      print(f"\n{BOLD}{CYAN}{'─'*50}{RESET}\n {BOLD}{t}{RESET}\n{BOLD}{CYAN}{'─'*50}{RESET}")
def ok(t):          print(f"  {GREEN}✔ {t}{RESET}")
def erro(t):        print(f"  {RED}✘ {t}{RESET}")
def info(t):        print(f"  {YELLOW}ℹ {t}{RESET}")
def separador():    print(f"  {GRAY}{'·'*46}{RESET}")

# ─── Banco de dados ───────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pendencias.db")

def conectar():
    return sqlite3.connect(DB_PATH)

def inicializar_db():
    with conectar() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS pessoas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nome    TEXT UNIQUE NOT NULL,
            criado  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS transacoes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            pessoa_id    INTEGER NOT NULL,
            descricao    TEXT NOT NULL,
            valor_total  REAL NOT NULL,
            dividido_por INTEGER NOT NULL DEFAULT 2,
            direcao      TEXT NOT NULL,
            pago         INTEGER DEFAULT 0,
            origem       TEXT DEFAULT 'manual',
            sheets_id    TEXT,
            data         TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (pessoa_id) REFERENCES pessoas(id)
        );

        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );

        CREATE TABLE IF NOT EXISTS pix_processados (
            sheets_id TEXT PRIMARY KEY,
            processado_em TEXT DEFAULT (datetime('now','localtime'))
        );

        INSERT OR IGNORE INTO config (chave, valor) VALUES
            ('revisao_dia_semana', '0'),
            ('revisao_hora',       '09:00'),
            ('ultima_revisao',     ''),
            ('sheets_id',          ''),
            ('sheets_aba',         'Página 1'),
            ('ultima_sync',        '');
        """)

# ─── Google Sheets ────────────────────────────────────────────────────────────
def sheets_configurado():
    creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
    sid = get_config("sheets_id") or ""
    return os.path.exists(creds_path) and sid.strip() != ""

def _conectar_sheets():
    """Autentica e retorna o objeto Spreadsheet, ou None em caso de erro."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc.open_by_key(get_config("sheets_id"))
    except Exception as e:
        erro(f"Erro ao conectar ao Sheets: {e}")
        return None

def carregar_sheets():
    """Retorna a aba de transações configurada ou None."""
    sh = _conectar_sheets()
    if not sh:
        return None
    try:
        return sh.worksheet(get_config("sheets_aba") or "Página 1")
    except Exception as e:
        erro(f"Erro ao abrir aba: {e}")
        return None

def buscar_pix_novos():
    """
    Lê a planilha e retorna transações PIX ainda não processadas.
    Retorna lista de dicts: {sheets_id, data, descricao, valor, categoria}
    """
    ws = carregar_sheets()
    if not ws:
        return []

    try:
        # Lê todos os valores brutos para evitar erro de cabeçalhos duplicados/vazios
        todas_linhas = ws.get_all_values()
    except Exception as e:
        erro(f"Erro ao ler planilha: {e}")
        return []

    if len(todas_linhas) < 2:
        return []

    # Detecta automaticamente a linha do cabeçalho procurando por "Tipo" ou "Descri"
    idx_cabecalho = None
    for i, linha in enumerate(todas_linhas):
        valores = [c.strip().lower() for c in linha]
        if "tipo" in valores and any(v in valores for v in ["descricao", "descrição", "description"]):
            idx_cabecalho = i
            break

    if idx_cabecalho is None:
        erro("Não foi possível encontrar a linha de cabeçalho na planilha.")
        return []

    cabecalho = [c.strip() for c in todas_linhas[idx_cabecalho]]
    # Dados comeam na linha seguinte ao cabecalho
    linhas_dados = todas_linhas[idx_cabecalho + 1:]

    # Mapeia nomes de colunas para índices (case-insensitive, aceita variações com acento)
    def achar_col(nomes):
        for nome in nomes:
            for i, c in enumerate(cabecalho):
                if c.lower() == nome.lower():
                    return i
        return None

    idx_tipo      = achar_col(["Tipo"])
    idx_id        = achar_col(["ID", "Id"])
    idx_descricao = achar_col(["Descrição", "Descricao", "Description"])
    idx_categoria = achar_col(["Categoria", "Category"])
    idx_valor     = achar_col(["Valor", "Value"])
    idx_data      = achar_col(["Data", "Date"])

    if any(i is None for i in [idx_tipo, idx_id, idx_descricao, idx_valor]):
        erro(f"Colunas esperadas não encontradas. Cabeçalho detectado: {cabecalho}")
        return []

    # Busca IDs já processados
    with conectar() as con:
        processados = {r[0] for r in con.execute("SELECT sheets_id FROM pix_processados").fetchall()}

    def cel(linha, idx):
        if idx is None or idx >= len(linha):
            return ""
        return str(linha[idx]).strip()

    novos = []
    for linha in linhas_dados:
        if not any(linha):
            continue

        tipo      = cel(linha, idx_tipo).upper()
        sheets_id = cel(linha, idx_id)
        descricao = cel(linha, idx_descricao)
        categoria = cel(linha, idx_categoria) if idx_categoria is not None else ""

        if tipo != "PIX":
            continue
        if not sheets_id or sheets_id in processados:
            continue
        if "same person" in categoria.lower():
            continue

        try:
            valor = float(cel(linha, idx_valor).replace(",", "."))
        except:
            continue

        novos.append({
            "sheets_id": sheets_id,
            "data":      cel(linha, idx_data) if idx_data is not None else "",
            "descricao": descricao,
            "valor":     valor,
            "categoria": categoria,
        })

    return novos

def marcar_pix_processado(sheets_id: str):
    with conectar() as con:
        con.execute("INSERT OR IGNORE INTO pix_processados (sheets_id) VALUES (?)", (sheets_id,))

def extrair_nome_pix(descricao: str) -> str:
    """
    Tenta extrair o nome da pessoa da descrição do PIX.
    Ex: 'PIX TRANSF LUCAS C10/02' → 'Lucas'
         'PIX TRANSF ARTHUR 10/02' → 'Arthur'
    """
    desc = descricao.upper()
    # Remove prefixos comuns
    for prefixo in ["PIX TRANSF ", "PIX TRANSFER ", "TRANSF PIX ", "PIX QRS ", "PIX "]:
        if desc.startswith(prefixo):
            desc = desc[len(prefixo):]
            break
    # Pega a primeira palavra (nome) — remove sufixos de data colados como "08/02"
    partes = desc.split()
    if partes:
        nome = re.sub(r'[\d/]+$', '', partes[0]).strip().capitalize()
        # Remove se for só número ou data
        if not nome or re.match(r'^\d', nome):
            return ""
        return nome
    return ""


def carregar_aba_pendencias():
    """Retorna a aba Página2 (cria se não existir) ou None."""
    sh = _conectar_sheets()
    if not sh:
        return None
    try:
        return sh.worksheet("Página2")
    except Exception:
        return sh.add_worksheet(title="Página2", rows=500, cols=5)


def sincronizar_pendencias_sheets():
    """
    Sincroniza o saldo líquido por pessoa na coluna A da Página2.
    Uma linha por pessoa, mostrando apenas o resultado final (positivo - negativo).
    Pessoas com saldo zero (quitadas) não aparecem.
    """
    if not sheets_configurado():
        return

    ws = carregar_aba_pendencias()
    if not ws:
        return

    try:
        # Calcula saldo líquido por pessoa (mais antiga primeiro)
        with conectar() as con:
            pessoas = con.execute("""
                SELECT DISTINCT p.id, p.nome, MIN(t.data) as primeira_data
                FROM transacoes t
                JOIN pessoas p ON p.id = t.pessoa_id
                WHERE t.pago = 0
                GROUP BY p.id, p.nome
                ORDER BY primeira_data ASC
            """).fetchall()

        linhas = []
        for pid, nome, _ in pessoas:
            saldo, eles, eu = saldo_pessoa(pid)
            if saldo == 0:
                continue  # quitado, não envia
            if saldo > 0:
                linha = f"{nome} te deve R$ {saldo:.2f}"
            else:
                linha = f"Você deve R$ {abs(saldo):.2f} para {nome}"
            linhas.append([linha])

        # Limpa e reescreve
        ws.clear()
        if linhas:
            ws.update(range_name=f"A1:A{len(linhas)}", values=linhas)

    except Exception as e:
        erro(f"Erro ao sincronizar Página2: {e}")

# ─── CRUD pessoas / transações ────────────────────────────────────────────────
def listar_pessoas():
    with conectar() as con:
        return con.execute("SELECT id, nome FROM pessoas ORDER BY nome").fetchall()

def criar_pessoa(nome: str) -> bool:
    nome = nome.strip().title()
    try:
        with conectar() as con:
            con.execute("INSERT INTO pessoas (nome) VALUES (?)", (nome,))
        return True
    except sqlite3.IntegrityError:
        return False

def buscar_pessoa(nome: str):
    with conectar() as con:
        return con.execute(
            "SELECT id, nome FROM pessoas WHERE lower(nome)=lower(?)", (nome,)
        ).fetchone()

def deletar_pessoa(pessoa_id: int):
    with conectar() as con:
        con.execute("DELETE FROM transacoes WHERE pessoa_id=?", (pessoa_id,))
        con.execute("DELETE FROM pessoas WHERE id=?", (pessoa_id,))

def registrar_transacao(pessoa_id, descricao, valor_total, dividido_por, direcao,
                         origem="manual", sheets_id=None):
    with conectar() as con:
        con.execute("""
            INSERT INTO transacoes
                (pessoa_id, descricao, valor_total, dividido_por, direcao, origem, sheets_id)
            VALUES (?,?,?,?,?,?,?)
        """, (pessoa_id, descricao, valor_total, dividido_por, direcao, origem, sheets_id))

def listar_transacoes_abertas(pessoa_id):
    with conectar() as con:
        return con.execute("""
            SELECT id, descricao, valor_total, dividido_por, direcao, data, origem
            FROM transacoes WHERE pessoa_id=? AND pago=0
            ORDER BY data DESC
        """, (pessoa_id,)).fetchall()

def quitar_transacao(transacao_id):
    with conectar() as con:
        con.execute("UPDATE transacoes SET pago=1 WHERE id=?", (transacao_id,))

def quitar_todas(pessoa_id):
    with conectar() as con:
        con.execute("UPDATE transacoes SET pago=1 WHERE pessoa_id=? AND pago=0", (pessoa_id,))

def saldo_pessoa(pessoa_id):
    with conectar() as con:
        rows = con.execute("""
            SELECT valor_total, dividido_por, direcao
            FROM transacoes WHERE pessoa_id=? AND pago=0
        """, (pessoa_id,)).fetchall()
    eles = sum(v/d for v,d,dr in rows if dr == "eles_devem")
    eu   = sum(v/d for v,d,dr in rows if dr == "eu_devo")
    return round(eles - eu, 2), round(eles, 2), round(eu, 2)

def resumo_geral():
    resultado = []
    for pid, nome in listar_pessoas():
        saldo, eles, eu = saldo_pessoa(pid)
        if saldo != 0:
            resultado.append((nome, saldo, eles, eu))
    return resultado

# ─── Config ───────────────────────────────────────────────────────────────────
def get_config(chave):
    with conectar() as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

def set_config(chave, valor):
    with conectar() as con:
        con.execute("INSERT OR REPLACE INTO config(chave,valor) VALUES(?,?)", (chave, valor))

# ─── UI helpers ───────────────────────────────────────────────────────────────
def escolher_pessoa(prompt="Escolha uma pessoa", permitir_criar=False) -> Optional[tuple]:
    pessoas = listar_pessoas()
    if not pessoas and not permitir_criar:
        erro("Nenhuma pessoa cadastrada ainda.")
        return None
    print(f"\n  {BOLD}{prompt}:{RESET}")
    for i, (pid, nome) in enumerate(pessoas, 1):
        saldo, _, _ = saldo_pessoa(pid)
        cor_s = GREEN if saldo > 0 else RED if saldo < 0 else GRAY
        tag   = f"[{cor_s}R$ {abs(saldo):.2f}{RESET}]" if saldo != 0 else f"[{GRAY}quitado{RESET}]"
        print(f"    {CYAN}{i}.{RESET} {nome} {tag}")
    if permitir_criar:
        print(f"    {YELLOW}N.{RESET} Criar nova pessoa")
    print(f"    {GRAY}0. Cancelar{RESET}")
    while True:
        raw = input(f"\n  → ").strip()
        if raw == "0":
            return None
        if permitir_criar and raw.upper() == "N":
            novo_nome = input("  Nome da nova pessoa: ").strip()
            if not novo_nome:
                erro("Nome vazio.")
                continue
            if criar_pessoa(novo_nome):
                ok(f"'{novo_nome.title()}' criado(a) e vinculado(a)!")
            else:
                info(f"'{novo_nome.title()}' já existe, usando cadastro existente.")
            return buscar_pessoa(novo_nome)
        if raw.isdigit() and 1 <= int(raw) <= len(pessoas):
            return pessoas[int(raw)-1]
        erro("Opção inválida.")

def input_valor(prompt) -> Optional[float]:
    while True:
        raw = input(f"  {prompt}: R$ ").strip().replace(",", ".")
        if raw == "":
            return None
        try:
            v = float(raw)
            if v <= 0: raise ValueError
            return v
        except ValueError:
            erro("Valor inválido.")

def input_int(prompt, minv, maxv) -> Optional[int]:
    while True:
        raw = input(f"  {prompt} ({minv}-{maxv}): ").strip()
        if raw == "":
            return None
        if raw.isdigit() and minv <= int(raw) <= maxv:
            return int(raw)
        erro("Número inválido.")

# ─── Tela: processar PIX do Sheets ───────────────────────────────────────────
def tela_processar_pix(pix_lista=None, silencioso=False):
    """
    Busca PIX novos no Sheets e pergunta ao usuário o que fazer com cada um.
    Se pix_lista for fornecida, usa ela (para revisão semanal).
    """
    if not sheets_configurado():
        erro("Google Sheets não configurado. Acesse Configurações → Sheets.")
        return

    if pix_lista is None:
        info("Buscando transações PIX novas na planilha...")
        pix_lista = buscar_pix_novos()

    if not pix_lista:
        if not silencioso:
            ok("Nenhuma transação PIX nova encontrada.")
        return

    print(f"\n  {BOLD}{YELLOW}🔔 {len(pix_lista)} transação(ões) PIX encontrada(s):{RESET}\n")

    for pix in pix_lista:
        sid       = pix["sheets_id"]
        descricao = pix["descricao"]
        valor     = pix["valor"]
        data      = pix["data"]
        sinal     = "+" if valor > 0 else ""
        cor_v     = GREEN if valor > 0 else RED

        print(f"  {BOLD}{'─'*46}{RESET}")
        print(f"  📅 {GRAY}{data}{RESET}")
        print(f"  📝 {descricao}")
        print(f"  💰 {cor_v}{sinal}R$ {valor:.2f}{RESET}")

        # Tenta identificar a pessoa automaticamente
        nome_detectado = extrair_nome_pix(descricao)
        pessoa_match = buscar_pessoa(nome_detectado) if nome_detectado else None

        if pessoa_match:
            print(f"  🔍 Pessoa detectada: {CYAN}{pessoa_match[1]}{RESET}")

        print(f"\n  O que fazer com esse PIX?")
        print(f"    {CYAN}1.{RESET} Abater uma dívida existente")
        print(f"    {CYAN}2.{RESET} Registrar como novo gasto compartilhado")
        print(f"    {CYAN}3.{RESET} Ignorar (não processar agora)")
        print(f"    {CYAN}4.{RESET} Marcar como processado (sem vincular)")

        opcao = input("  → ").strip()

        if opcao == "1":
            _pix_abater_divida(pix, pessoa_match)
            marcar_pix_processado(sid)

        elif opcao == "2":
            _pix_novo_gasto(pix, pessoa_match)
            marcar_pix_processado(sid)

        elif opcao == "3":
            info("PIX ignorado por agora — aparecerá novamente na próxima sincronização.")

        elif opcao == "4":
            marcar_pix_processado(sid)
            ok("Marcado como processado.")

        print()

def _pix_abater_divida(pix, pessoa_sugerida):
    """Aplica o valor do PIX para quitar transações abertas de uma pessoa."""
    valor = abs(pix["valor"])

    # Confirma ou escolhe a pessoa
    if pessoa_sugerida:
        print(f"\n  Usar {CYAN}{pessoa_sugerida[1]}{RESET}? (S/n)")
        r = input("  → ").strip().lower()
        if r == "n":
            pessoa = escolher_pessoa("Vincular a quem?")
        else:
            pessoa = pessoa_sugerida
    else:
        pessoa = escolher_pessoa("Vincular a quem?")

    if not pessoa:
        return

    pid, nome = pessoa
    transacoes = listar_transacoes_abertas(pid)

    if not transacoes:
        info(f"Nenhuma pendência aberta com {nome}.")
        # Oferece registrar como novo
        print(f"  Registrar como novo gasto mesmo assim? (s/N)")
        if input("  → ").strip().lower() == "s":
            _pix_novo_gasto(pix, pessoa)
        return

    saldo, eles, eu = saldo_pessoa(pid)
    print(f"\n  {BOLD}Pendências abertas com {CYAN}{nome}{RESET}{BOLD}:{RESET}")
    for t in transacoes:
        tid, desc, vtotal, divpor, direcao, data, origem = t
        vc = vtotal / divpor
        cor_d = GREEN if direcao == "eles_devem" else RED
        seta  = "→ te deve" if direcao == "eles_devem" else "→ você deve"
        print(f"    [{tid}] {cor_d}R$ {vc:.2f}{RESET}  {desc}  {GRAY}({seta}){RESET}")

    print(f"\n  {BOLD}PIX de R$ {valor:.2f} — o que quitar?{RESET}")
    print(f"    {CYAN}1.{RESET} Quitar transação específica (pelo ID)")
    print(f"    {CYAN}2.{RESET} Quitar TODAS as pendências com {nome}")
    print(f"    {CYAN}3.{RESET} Registrar como abatimento parcial")

    sub = input("  → ").strip()

    if sub == "1":
        tid_raw = input("  ID da transação: ").strip()
        if tid_raw.isdigit():
            quitar_transacao(int(tid_raw))
            ok(f"Transação [{tid_raw}] quitada com o PIX de R$ {valor:.2f}!")
            sincronizar_pendencias_sheets()
        else:
            erro("ID inválido.")

    elif sub == "2":
        quitar_todas(pid)
        ok(f"Todas as pendências com {nome} quitadas com o PIX de R$ {valor:.2f}!")
        sincronizar_pendencias_sheets()

    elif sub == "3":
        # Registra como crédito/débito no valor exato do PIX
        direcao = "eles_devem" if pix["valor"] > 0 else "eu_devo"
        registrar_transacao(pid, f"Abatimento PIX: {pix['descricao']}",
                            valor, 1, direcao, origem="sheets", sheets_id=pix["sheets_id"])
        ok(f"Abatimento de R$ {valor:.2f} registrado para {nome}.")
        sincronizar_pendencias_sheets()

def _pix_novo_gasto(pix, pessoa_sugerida):
    """Registra o PIX como um novo gasto compartilhado."""
    valor = abs(pix["valor"])

    if pessoa_sugerida:
        print(f"\n  Usar {CYAN}{pessoa_sugerida[1]}{RESET}? (S/n)")
        r = input("  → ").strip().lower()
        if r != "n":
            pessoa = pessoa_sugerida
        else:
            pessoa = escolher_pessoa("Vincular a quem?", permitir_criar=True)
    else:
        pessoa = escolher_pessoa("Vincular a quem?", permitir_criar=True)

    if not pessoa:
        return

    pid, nome = pessoa

    print(f"\n  Descrição {GRAY}(Enter para usar '{pix['descricao']}'){RESET}: ")
    desc = input("  → ").strip() or pix["descricao"]

    print(f"\n  Dividido entre quantas pessoas? {GRAY}(padrão: 2){RESET}")
    divpor = input_int("  Pessoas", 2, 20) or 2

    print(f"\n  {BOLD}Quem pagou?{RESET}")
    print(f"    {CYAN}1.{RESET} Eu paguei → {nome} me deve R$ {valor/divpor:.2f}")
    print(f"    {CYAN}2.{RESET} {nome} pagou → Eu devo R$ {valor/divpor:.2f}")
    opcao = input("  → ").strip()

    if opcao == "1":
        direcao = "eles_devem"
    elif opcao == "2":
        direcao = "eu_devo"
    else:
        erro("Opção inválida.")
        return

    registrar_transacao(pid, desc, valor, divpor, direcao,
                        origem="sheets", sheets_id=pix["sheets_id"])
    ok(f"Gasto registrado! R$ {valor/divpor:.2f} vinculado a {nome}.")
    sincronizar_pendencias_sheets()

# ─── Telas principais ─────────────────────────────────────────────────────────
def tela_painel():
    titulo("💰 PAINEL DE PENDÊNCIAS")
    resumo = resumo_geral()
    if not resumo:
        info("Tudo zerado! Nenhuma pendência em aberto. 🎉")
        return

    te_devem  = [r for r in resumo if r[1] > 0]
    tem_divida = [r for r in resumo if r[1] < 0]

    if te_devem:
        print(f"\n  {BOLD}{GREEN}👉 Te devem:{RESET}")
        for nome, saldo, eles, eu in te_devem:
            print(f"     {nome:<18} {GREEN}+ R$ {saldo:.2f}{RESET}")

    if tem_divida:
        print(f"\n  {BOLD}{RED}👈 Você deve:{RESET}")
        for nome, saldo, eles, eu in tem_divida:
            print(f"     {nome:<18} {RED}- R$ {abs(saldo):.2f}{RESET}")

    total = sum(r[1] for r in resumo)
    separador()
    cor_t = GREEN if total >= 0 else RED
    sinal = "+" if total >= 0 else ""
    print(f"  {BOLD}Saldo líquido total:{RESET} {cor_t}{sinal}R$ {total:.2f}{RESET}\n")

    if sheets_configurado():
        pix = buscar_pix_novos()
        if pix:
            print(f"  {YELLOW}🔔 {len(pix)} PIX novo(s) na planilha aguardando revisão!{RESET}")

def tela_registrar_gasto():
    titulo("➕ REGISTRAR GASTO COMPARTILHADO")
    pessoa = escolher_pessoa("Com quem foi o gasto?")
    if not pessoa:
        return
    pid, nome = pessoa

    print(f"\n  {BOLD}Descrição:{RESET}")
    descricao = input("  → ").strip()
    if not descricao:
        erro("Descrição vazia.")
        return

    valor = input_valor("Valor total")
    if valor is None:
        return

    print(f"\n  Dividido entre quantas pessoas? {GRAY}(padrão: 2){RESET}")
    divpor = input_int("  Pessoas", 2, 20) or 2

    print(f"\n  {BOLD}Quem pagou?{RESET}")
    print(f"    {CYAN}1.{RESET} Eu paguei → {nome} me deve R$ {valor/divpor:.2f}")
    print(f"    {CYAN}2.{RESET} {nome} pagou → Eu devo R$ {valor/divpor:.2f}")
    opcao = input("  → ").strip()

    if opcao == "1":
        direcao, msg = "eles_devem", f"{nome} te deve R$ {valor/divpor:.2f}"
    elif opcao == "2":
        direcao, msg = "eu_devo", f"Você deve R$ {valor/divpor:.2f} para {nome}"
    else:
        erro("Opção inválida.")
        return

    registrar_transacao(pid, descricao, valor, divpor, direcao)
    ok(f"Registrado! {msg}")
    sincronizar_pendencias_sheets()

def tela_detalhe_pessoa():
    titulo("🔍 DETALHE DE PENDÊNCIAS")
    pessoa = escolher_pessoa()
    if not pessoa:
        return
    pid, nome = pessoa

    transacoes = listar_transacoes_abertas(pid)
    saldo, eles, eu = saldo_pessoa(pid)

    print(f"\n  {BOLD}Pendências abertas com {CYAN}{nome}{RESET}{BOLD}:{RESET}")
    if not transacoes:
        ok("Nenhuma pendência em aberto!")
        return

    for t in transacoes:
        tid, desc, vtotal, divpor, direcao, data, origem = t
        vc = vtotal / divpor
        if direcao == "eles_devem":
            linha = f"{GREEN}+R${vc:.2f}{RESET}  {desc}"
        else:
            linha = f"{RED}-R${vc:.2f}{RESET}  {desc}"
        tag_orig = f"{BLUE}[sheets]{RESET}" if origem == "sheets" else ""
        print(f"    [{tid}] {linha}  {GRAY}(total R${vtotal:.2f}÷{divpor} — {data[:10]}){RESET} {tag_orig}")

    separador()
    if saldo > 0:
        print(f"  Saldo: {GREEN}{nome} te deve R$ {saldo:.2f}{RESET}")
    elif saldo < 0:
        print(f"  Saldo: {RED}Você deve R$ {abs(saldo):.2f} para {nome}{RESET}")
    else:
        print(f"  Saldo: {GRAY}Quitado!{RESET}")

    print(f"\n  {BOLD}Ação:{RESET}")
    print(f"    {CYAN}1.{RESET} Quitar transação específica")
    print(f"    {CYAN}2.{RESET} Quitar TODAS com {nome}")
    print(f"    {CYAN}0.{RESET} Voltar")
    opcao = input("  → ").strip()

    if opcao == "1":
        tid_raw = input("  ID da transação: ").strip()
        if tid_raw.isdigit():
            quitar_transacao(int(tid_raw))
            ok("Transação quitada!")
            sincronizar_pendencias_sheets()
        else:
            erro("ID inválido.")
    elif opcao == "2":
        if input(f"  {YELLOW}Confirmar quitar tudo com {nome}? (s/N): {RESET}").strip().lower() == "s":
            quitar_todas(pid)
            ok(f"Todas as pendências com {nome} quitadas!")
            sincronizar_pendencias_sheets()

def tela_revisao_semanal(automatica=False):
    titulo("📋 REVISÃO SEMANAL")
    if automatica:
        print(f"\n  {YELLOW}🔔 Hora de revisar suas pendências da semana!{RESET}\n")

    resumo = resumo_geral()
    if not resumo:
        ok("Tudo zerado! Nenhuma pendência em aberto. 🎉")
    else:
        for nome, saldo, eles, eu_v in resumo:
            pid = buscar_pessoa(nome)[0]
            transacoes = listar_transacoes_abertas(pid)

            print(f"\n  {BOLD}{CYAN}{nome}{RESET}")
            separador()

            for t in transacoes:
                tid, desc, vtotal, divpor, direcao, data, origem = t
                vc = vtotal / divpor
                if direcao == "eles_devem":
                    print(f"    {GREEN}+ R$ {vc:.2f}{RESET}  {nome} te deve  {GRAY}({desc}){RESET}")
                else:
                    print(f"    {RED}- R$ {vc:.2f}{RESET}  Você deve para {nome}  {GRAY}({desc}){RESET}")

            separador()
            cor_s = GREEN if saldo > 0 else RED
            if saldo > 0:
                print(f"  Saldo: {cor_s}{nome} te deve R$ {saldo:.2f}{RESET}")
            else:
                print(f"  Saldo: {cor_s}Você deve R$ {abs(saldo):.2f} para {nome}{RESET}")

        total = sum(r[1] for r in resumo)
        print()
        separador()
        cor_t = GREEN if total >= 0 else RED
        print(f"  {BOLD}Saldo líquido total: {cor_t}R$ {total:+.2f}{RESET}\n")

    # Verifica PIX novos no Sheets
    if sheets_configurado():
        info("Verificando PIX novos na planilha...")
        pix_novos = buscar_pix_novos()
        if pix_novos:
            print(f"\n  {YELLOW}🔔 {len(pix_novos)} transação(ões) PIX encontrada(s) na planilha!{RESET}")
            print(f"  Deseja processar agora? (S/n)")
            if input("  → ").strip().lower() != "n":
                tela_processar_pix(pix_lista=pix_novos)
        else:
            ok("Nenhum PIX novo na planilha.")

    set_config("ultima_revisao", datetime.now().isoformat())

def tela_gerenciar_pessoas():
    titulo("👥 GERENCIAR PESSOAS")
    print(f"  {CYAN}1.{RESET} Adicionar pessoa")
    print(f"  {CYAN}2.{RESET} Remover pessoa")
    print(f"  {CYAN}0.{RESET} Voltar")
    opcao = input("  → ").strip()

    if opcao == "1":
        nome = input("  Nome: ").strip()
        if criar_pessoa(nome):
            ok(f"'{nome.title()}' adicionado(a)!")
        else:
            erro(f"'{nome.title()}' já existe.")
    elif opcao == "2":
        pessoa = escolher_pessoa("Quem remover?")
        if pessoa:
            pid, nome = pessoa
            if input(f"  {RED}Remover {nome} e suas pendências? (s/N): {RESET}").strip().lower() == "s":
                deletar_pessoa(pid)
                ok(f"{nome} removido(a).")

def tela_configuracoes():
    titulo("⚙️  CONFIGURAÇÕES")

    sheets_ok = sheets_configurado()
    sid = get_config("sheets_id") or ""
    aba = get_config("sheets_aba") or "Página 1"
    dia = int(get_config("revisao_dia_semana") or 0)
    hora = get_config("revisao_hora") or "09:00"
    dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]

    status_sheets = f"{GREEN}✔ Conectado{RESET}" if sheets_ok else f"{RED}✘ Não configurado{RESET}"
    print(f"\n  Google Sheets: {status_sheets}")
    if sid:
        print(f"  ID da planilha: {GRAY}{sid[:20]}...{RESET}")
        print(f"  Aba: {CYAN}{aba}{RESET}")
    print(f"  Revisão semanal: {CYAN}{dias[dia]}{RESET} às {CYAN}{hora}{RESET}\n")

    print(f"  {CYAN}1.{RESET} Configurar Google Sheets (ID da planilha)")
    print(f"  {CYAN}2.{RESET} Alterar nome da aba")
    print(f"  {CYAN}3.{RESET} Alterar dia da revisão semanal")
    print(f"  {CYAN}4.{RESET} Alterar horário da revisão")
    print(f"  {CYAN}5.{RESET} Testar conexão com Sheets")
    print(f"  {CYAN}0.{RESET} Voltar")

    opcao = input("  → ").strip()

    if opcao == "1":
        print(f"\n  Cole o ID da planilha (parte da URL entre /d/ e /edit):")
        print(f"  {GRAY}Ex: https://docs.google.com/spreadsheets/d/{{ID}}/edit{RESET}")
        novo_id = input("  → ").strip()
        if novo_id:
            set_config("sheets_id", novo_id)
            ok("ID salvo! Certifique-se de ter o credentials.json na mesma pasta.")
            info("Veja o README para instruções de como criar a Service Account.")

    elif opcao == "2":
        nova_aba = input(f"  Nome da aba {GRAY}(atual: {aba}){RESET}: ").strip()
        if nova_aba:
            set_config("sheets_aba", nova_aba)
            ok(f"Aba configurada para '{nova_aba}'.")

    elif opcao == "3":
        for i, d in enumerate(dias):
            print(f"    {CYAN}{i}.{RESET} {d}")
        d = input_int("  Dia", 0, 6)
        if d is not None:
            set_config("revisao_dia_semana", str(d))
            ok(f"Revisão: {dias[d]}.")

    elif opcao == "4":
        h = input("  Horário (HH:MM): ").strip()
        try:
            datetime.strptime(h, "%H:%M")
            set_config("revisao_hora", h)
            ok(f"Horário: {h}.")
        except ValueError:
            erro("Formato inválido. Use HH:MM.")

    elif opcao == "5":
        if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")):
            erro("credentials.json não encontrado na pasta do bot.")
            return
        info("Conectando...")
        ws = carregar_sheets()
        if ws:
            ok(f"Conectado! Aba '{ws.title}' encontrada.")
        else:
            erro("Falha na conexão. Verifique o ID e o credentials.json.")

# ─── Revisão automática ───────────────────────────────────────────────────────
def verificar_revisao():
    dia_conf  = int(get_config("revisao_dia_semana") or 0)
    hora_conf = get_config("revisao_hora") or "09:00"
    ultima    = get_config("ultima_revisao") or ""
    agora = datetime.now()
    if agora.weekday() != dia_conf:
        return False
    h, m = hora_conf.split(":")
    hora_alvo = agora.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if abs((agora - hora_alvo).total_seconds()) > 3600:
        return False
    if ultima:
        try:
            if (agora - datetime.fromisoformat(ultima)).days < 6:
                return False
        except:
            pass
    return True

# ─── Menu principal ───────────────────────────────────────────────────────────
def cabecalho():
    os.system("cls" if os.name == "nt" else "clear")
    sheets_tag = f" {GREEN}● Sheets{RESET}" if sheets_configurado() else f" {GRAY}○ Sheets{RESET}"
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════╗
║        💸  BOT DE PENDÊNCIAS  💸             ║
╚══════════════════════════════════════════════╝{RESET}{sheets_tag}""")

def menu_principal():
    inicializar_db()

    if verificar_revisao():
        cabecalho()
        tela_revisao_semanal(automatica=True)
        input(f"\n  {GRAY}[Enter para continuar]{RESET}")

    while True:
        cabecalho()
        tela_painel()

        print(f"\n  {BOLD}O que deseja fazer?{RESET}")
        print(f"  {CYAN}1.{RESET} ➕  Registrar gasto manualmente")
        print(f"  {CYAN}2.{RESET} 🔍  Ver detalhes / quitar pendências")
        print(f"  {CYAN}3.{RESET} 📱  Processar PIX do Google Sheets")
        print(f"  {CYAN}4.{RESET} 📋  Revisão semanal agora")
        print(f"  {CYAN}5.{RESET} 👥  Gerenciar pessoas")
        print(f"  {CYAN}6.{RESET} ⚙️   Configurações")
        print(f"  {CYAN}0.{RESET} 🚪  Sair")

        opcao = input(f"\n  {BOLD}→ {RESET}").strip()

        if   opcao == "1": tela_registrar_gasto()
        elif opcao == "2": tela_detalhe_pessoa()
        elif opcao == "3": tela_processar_pix()
        elif opcao == "4": tela_revisao_semanal()
        elif opcao == "5": tela_gerenciar_pessoas()
        elif opcao == "6": tela_configuracoes()
        elif opcao == "0":
            print(f"\n  {GREEN}Até logo! 👋{RESET}\n")
            sys.exit(0)
        else:
            erro("Opção inválida.")

        if opcao in ("1","2","3","4","5","6"):
            input(f"\n  {GRAY}[Enter para voltar ao menu]{RESET}")

if __name__ == "__main__":
    menu_principal()
