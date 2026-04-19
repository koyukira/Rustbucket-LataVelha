import requests
import json
import sys
import os
import re
import shutil
import subprocess
import threading
import urllib.parse
import socketserver
import tkinter as tk
import mimetypes
import time
from tkinter import filedialog
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────
URL        = "http://localhost:8080/v1/chat/completions"
MODELO     = "qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"
PASTA_TEMP = "./temp_lata_velha"
PORTA_UI   = 12314
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
FENCE      = '`' * 3
# ──────────────────────────────────────────────────────────────

# Sistema de Tags XML que a IA usa para sinalizar tipo de resposta:
#   <falar>...</falar>              → mensagem ao usuário
#   <pensar>...</pensar>            → raciocínio interno
#   <codar> ```arq.ext ... ``` </codar>  → criar/sobrescrever arquivo
#   <editar arquivo="arq.ext"> <<< → patch cirúrgico
#   <instalar>pacote</instalar>     → pip install
#   <renomear>velho|novo</renomear> → renomear arquivo
#   <executar/>                     → rodar projeto

SISTEMA_CRIAR = (
    "Você é um desenvolvedor sênior autônomo. Responda SEMPRE usando tags XML para separar os tipos de conteúdo.\n"
    "\n"
    "TAGS DISPONÍVEIS:\n"
    "\n"
    "<falar>Sua mensagem ao usuário aqui</falar>\n"
    "  → Use para TODA comunicação: saudações, explicações, perguntas, confirmações.\n"
    "  → Se o usuário mandou só uma saudação ou pergunta sem código, responda APENAS com <falar>.\n"
    "  → Obrigatório quando não há código.\n"
    "\n"
    f"<codar>\n{FENCE}nome_do_arquivo.ext\n<código completo>\n{FENCE}\n</codar>\n"
    "  → Para CRIAR ou SOBRESCREVER um arquivo inteiro.\n"
    "  → O nome do arquivo vai na primeira linha da fence. Pode incluir subpastas: assets/sprites.js\n"
    "  → NUNCA use '...' ou omita partes. Código SEMPRE completo.\n"
    "\n"
    "<instalar>nome_pacote</instalar>\n"
    "  → Para instalar dependências Python via pip.\n"
    "\n"
    "<executar/>\n"
    "  → Para rodar o projeto após criá-lo.\n"
    "\n"
    "EXEMPLOS:\n"
    "\n"
    "Usuário: 'oi'\n"
    "<falar>Oi! Como posso ajudar com seu projeto?</falar>\n"
    "\n"
    "Usuário: 'crie um jogo da cobrinha em html'\n"
    "<falar>Criando o jogo da cobrinha em HTML!</falar>\n"
    "<codar>\n"
    f"{FENCE}index.html\n"
    "<!DOCTYPE html>...\n"
    f"{FENCE}\n"
    "</codar>\n"
    "<executar/>\n"
)

SISTEMA_EDITAR = (
    "Você é um engenheiro de software sênior especialista em cirurgia de código.\n"
    "Responda SEMPRE usando tags XML para separar os tipos de conteúdo.\n"
    "\n"
    "TAGS DISPONÍVEIS:\n"
    "\n"
    "<falar>Mensagem ao usuário</falar>\n"
    "  → Para toda comunicação: explicar o que fez, tirar dúvidas, dar avisos.\n"
    "  → Se o usuário mandou só uma saudação ou pergunta sem pedir código, responda APENAS com <falar>.\n"
    "\n"
    "<editar arquivo=\"caminho/do/arquivo.ext\">\n"
    "<<<ANTES>>>\n"
    "<trecho EXATO que existe no arquivo — copie literalmente>\n"
    "<<<DEPOIS>>>\n"
    "<trecho novo completo>\n"
    "<<<FIM>>>\n"
    "</editar>\n"
    "  → Para MODIFICAR arquivo existente de forma cirúrgica.\n"
    "  → REGRA DE OURO: Nunca reescreva o arquivo inteiro para mudança pequena.\n"
    "  → <<<ANTES>>> deve ser copiado PALAVRA POR PALAVRA do arquivo original.\n"
    "  → Inclua contexto suficiente para ser único no arquivo (mínimo 2-3 linhas).\n"
    "  → Dentro do <<<DEPOIS>>>, o bloco COMPLETO. NUNCA use '...'.\n"
    "  → Você pode ter vários blocos <<<ANTES>>>/<<<DEPOIS>>> na mesma tag <editar>.\n"
    "\n"
    f"<codar>\n{FENCE}caminho/novo_arquivo.ext\n<código completo>\n{FENCE}\n</codar>\n"
    "  → APENAS para criar arquivo NOVO do zero. O caminho pode incluir subpastas: assets/sprites.js\n"
    "  → Ou se o arquivo tiver < 30 linhas e precisar mudar mais de 50%.\n"
    "\n"
    "<instalar>nome_pacote</instalar>\n"
    "  → Para instalar dependências Python via pip.\n"
    "\n"
    "<renomear>arquivo_antigo.ext|arquivo_novo.ext</renomear>\n"
    "  → Para renomear um arquivo. Separe com pipe |.\n"
    "\n"
    "<executar/>\n"
    "  → Para rodar o projeto.\n"
    "\n"
    "══════════════════════════════════════════════\n"
    "QUANDO USAR <editar> vs <codar>?\n"
    "  <editar> → qualquer mudança em arquivo EXISTENTE\n"
    "  <codar>  → somente arquivo NOVO (inclusive em subpastas)\n"
    "══════════════════════════════════════════════\n"
    "\n"
    "EXEMPLOS CORRETOS:\n"
    "\n"
    "Usuário: 'oi'\n"
    "<falar>Oi! O que vamos ajustar no projeto?</falar>\n"
    "\n"
    "Usuário: 'mude a cor da cobra para azul'\n"
    "<falar>Trocando a cor da cobra para azul!</falar>\n"
    "<editar arquivo=\"index.html\">\n"
    "<<<ANTES>>>\n"
    "  snakeColor = '#4CAF50';\n"
    "<<<DEPOIS>>>\n"
    "  snakeColor = '#1a6cb5';\n"
    "<<<FIM>>>\n"
    "</editar>\n"
    "\n"
    "Usuário: 'crie arquivo de sprites em assets/sprites.js'\n"
    "<falar>Criando assets/sprites.js!</falar>\n"
    "<codar>\n"
    f"{FENCE}assets/sprites.js\n"
    "// sprites data...\n"
    f"{FENCE}\n"
    "</codar>\n"
)

SISTEMA_COMPACT = (
    "Você é um assistente técnico especialista em resumo de contexto de desenvolvimento.\n"
    "Você receberá o histórico completo de uma sessão de trabalho em código.\n"
    "Produza um resumo DENSO e TÉCNICO em português que preserve:\n"
    "- Estado atual de CADA arquivo do projeto (estrutura, responsabilidade, funções principais)\n"
    "- Decisões de arquitetura tomadas\n"
    "- Bugs encontrados e como foram resolvidos\n"
    "- Features implementadas e pendentes\n"
    "- Qualquer contexto crítico que um dev precisaria para continuar o trabalho\n"
    "Seja conciso mas completo. Sem introduções ou conclusões desnecessárias.\n"
    "Formato: seções com ## para cada área importante.\n"
)

# ── Estado global ────────────────────────────────────────────────
proj = {
    "pasta_orig":   None,
    "pasta_work":   None,
    "arquivo":      None,
    "historico":    [],
    "entrypoint":   "main.py",
    "setup_feito":  False,      # True após carregar projeto inicial
    "resumo_c1":    None,       # Texto do /compact
    "ctx_tokens":   0,          # Estimativa de tokens no contexto atual
    "ctx_chars":    0,          # Chars do contexto atual
}

# Buffer de mensagens tipadas para a UI
msg_buffer  = []
msg_lock    = threading.Lock()
# Buffer de linhas de sistema (compatibilidade)
output_buffer = []
output_lock   = threading.Lock()
proc_ativo    = None
IGNORAR = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.idea', 'temp_lata_velha'}

# ── Emissores ────────────────────────────────────────────────────

def push_msg(tipo, conteudo):
    with msg_lock:
        msg_buffer.append({"tipo": tipo, "conteudo": conteudo.rstrip()})
        if len(msg_buffer) > 800:
            msg_buffer.pop(0)

def log_output(linha):
    linha = linha.rstrip()
    with output_lock:
        output_buffer.append(linha)
        if len(output_buffer) > 500:
            output_buffer.pop(0)
    push_msg("sistema", linha)
    sys.stdout.write(linha + "\n")
    sys.stdout.flush()


# ── Contexto inteligente ─────────────────────────────────────────

MAX_LINHAS_JSON_AMOSTRA = 60   # linhas de amostra para arquivos JSON

def resumir_json(conteudo, caminho_rel):
    """Retorna uma representação estrutural do JSON, não o conteúdo completo."""
    try:
        dados = json.loads(conteudo)
    except Exception:
        # JSON inválido — trata como texto normal, truncado
        linhas = conteudo.split('\n')
        amostra = '\n'.join(linhas[:MAX_LINHAS_JSON_AMOSTRA])
        return f"[JSON inválido — primeiras {MAX_LINHAS_JSON_AMOSTRA} linhas]\n{amostra}"

    def descrever(v, profundidade=0, max_prof=3):
        indent = "  " * profundidade
        if isinstance(v, dict):
            if profundidade >= max_prof:
                return f"{{...{len(v)} chaves}}"
            linhas = ["{"]
            for k, val in list(v.items())[:20]:
                desc = descrever(val, profundidade+1, max_prof)
                linhas.append(f"{indent}  {json.dumps(k)}: {desc}")
            if len(v) > 20:
                linhas.append(f"{indent}  ...+{len(v)-20} chaves")
            linhas.append(f"{indent}}}")
            return "\n".join(linhas)
        elif isinstance(v, list):
            if not v:
                return "[]"
            if profundidade >= max_prof:
                return f"[...{len(v)} itens]"
            tipo_item = descrever(v[0], profundidade+1, max_prof)
            return f"[{len(v)} itens, ex: {tipo_item}]"
        elif isinstance(v, str):
            return f'"{v[:40]}{"..." if len(v)>40 else ""}"'
        else:
            return repr(v)

    estrutura = descrever(dados)
    total_linhas = conteudo.count('\n') + 1
    return f"[JSON — {total_linhas} linhas — estrutura]\n{estrutura}"


def montar_contexto_inteligente(pasta_work, arquivo_ativo, entrypoint):
    MAX_LINHAS_TOTAL   = 5000
    MAX_LINHAS_ARQUIVO = 2500
    todos_arquivos = []
    try:
        for p in Path(pasta_work).rglob('*'):
            if p.is_file() and not any(ign in p.parts for ign in IGNORAR) and not p.name.startswith('.'):
                todos_arquivos.append(p)
    except:
        pass

    prioridades = []
    if arquivo_ativo:
        p = Path(arquivo_ativo)
        if p.exists(): prioridades.append(p)
    if entrypoint:
        p = Path(pasta_work) / entrypoint
        if p.exists() and p not in prioridades: prioridades.append(p)
    for f in todos_arquivos:
        if f not in prioridades: prioridades.append(f)

    linhas_total = 0
    contexto = []
    ignorados = []
    for idx, f in enumerate(prioridades):
        try:
            rel = f.relative_to(pasta_work).as_posix()
            conteudo = f.read_text(encoding='utf-8')
            qtd = conteudo.count('\n') + 1
            prioritario = idx < 2
            eh_json = f.suffix.lower() == '.json'

            if eh_json:
                # JSON: nunca incluir código completo, só estrutura
                resumo = resumir_json(conteudo, rel)
                contexto.append(f"--- ARQUIVO: {rel} (JSON — estrutura apenas) ---\n{FENCE}\n{resumo}\n{FENCE}\n")
                linhas_total += min(qtd, MAX_LINHAS_JSON_AMOSTRA + 10)
            elif prioritario:
                contexto.append(f"--- ARQUIVO: {rel} ---\n{FENCE}\n{conteudo}\n{FENCE}\n")
                linhas_total += qtd
            elif qtd > MAX_LINHAS_ARQUIVO and linhas_total + MAX_LINHAS_ARQUIVO <= MAX_LINHAS_TOTAL:
                trecho = '\n'.join(conteudo.split('\n')[:MAX_LINHAS_ARQUIVO])
                contexto.append(f"--- ARQUIVO: {rel} (truncado, {qtd} linhas) ---\n{FENCE}\n{trecho}\n...\n{FENCE}\n")
                linhas_total += MAX_LINHAS_ARQUIVO
            elif linhas_total + qtd <= MAX_LINHAS_TOTAL:
                contexto.append(f"--- ARQUIVO: {rel} ---\n{FENCE}\n{conteudo}\n{FENCE}\n")
                linhas_total += qtd
            else:
                ignorados.append(rel)
        except:
            try: ignorados.append(f.relative_to(pasta_work).as_posix() + " (binário)")
            except: pass

    ativo_rel = ""
    if arquivo_ativo:
        try: ativo_rel = Path(arquivo_ativo).relative_to(pasta_work).as_posix()
        except: ativo_rel = arquivo_ativo

    cab = f"CÓDIGO FONTE ATUAL DO PROJETO:\n"
    if ativo_rel: cab += f"(Arquivo aberto no editor: {ativo_rel})\n"
    cab += "\n"
    resultado = cab + "\n".join(contexto)
    if ignorados:
        resultado += "\nOUTROS ARQUIVOS (omitidos por tamanho):\n" + "\n".join(f" - {i}" for i in ignorados) + "\n"

    # Atualizar mapa de contexto
    proj["ctx_chars"] = len(resultado)
    proj["ctx_tokens"] = len(resultado) // 4  # estimativa ~4 chars/token

    return resultado


def montar_contexto_completo(pasta_work):
    """Carrega TODOS os arquivos sem limite de tamanho para a fase de setup."""
    todos_arquivos = []
    try:
        for p in Path(pasta_work).rglob('*'):
            if p.is_file() and not any(ign in p.parts for ign in IGNORAR) and not p.name.startswith('.'):
                todos_arquivos.append(p)
    except:
        pass

    contexto = []
    total_chars = 0
    for f in sorted(todos_arquivos, key=lambda p: (p.is_dir(), p.name)):
        try:
            rel = f.relative_to(pasta_work).as_posix()
            conteudo = f.read_text(encoding='utf-8')
            eh_json = f.suffix.lower() == '.json'

            if eh_json:
                resumo = resumir_json(conteudo, rel)
                bloco = f"--- ARQUIVO: {rel} (JSON — estrutura apenas) ---\n{FENCE}\n{resumo}\n{FENCE}\n"
            else:
                bloco = f"--- ARQUIVO: {rel} ---\n{FENCE}\n{conteudo}\n{FENCE}\n"

            contexto.append(bloco)
            total_chars += len(bloco)
        except:
            try: contexto.append(f"--- ARQUIVO: {rel} (binário/ilegível) ---\n")
            except: pass

    resultado = "PROJETO COMPLETO — SETUP INICIAL:\n\n" + "\n".join(contexto)
    proj["ctx_chars"] = total_chars
    proj["ctx_tokens"] = total_chars // 4
    return resultado


# ── Parsers de Tags XML ──────────────────────────────────────────

def tag_contents(texto, tag):
    return re.findall(rf"<{tag}(?:\s[^>]*)?>(.+?)</{tag}>", texto, re.DOTALL)

def tag_attr_contents(texto, tag, attr):
    return re.findall(rf'<{tag}\s+{attr}="([^"]+)">(.*?)</{tag}>', texto, re.DOTALL)

def extrair_cercas(texto):
    cercas = {}
    mapa = {"python":"main.py","py":"main.py","javascript":"script.js","js":"script.js",
            "node":"script.js","html":"index.html","css":"style.css","java":"Main.java",
            "c":"main.c","cpp":"main.cpp","typescript":"script.ts","ts":"script.ts"}
    for bloco in tag_contents(texto, "codar"):
        for nome_raw, codigo in re.findall(r"`{3,}([^\n]*)\n(.*?)`{3,}", bloco, re.DOTALL):
            nome = nome_raw.strip()
            codigo = codigo.strip()
            primeira = codigo.split('\n')[0].strip()

            # 1) Primeira linha do código tem comentário com caminho? ex: // assets/sprites.js
            m = re.search(r'^(?:\/\/|#|\/\*|<!--)\s*([\w\-\.\/\\]+\.\w+)', primeira)
            if m:
                nome_final = m.group(1).replace('\\', '/')
            # 2) O nome da fence já tem extensão (pode ter subpastas)? ex: assets/sprites.json
            elif re.search(r'\.\w+$', nome):
                nome_final = nome  # preserva subpastas como assets/sprites.json
            # 3) É uma linguagem conhecida sem caminho?
            elif nome.lower() in mapa:
                nome_final = mapa[nome.lower()]
            # 4) Makefile/Dockerfile sem extensão
            elif nome.lower() in ["makefile", "dockerfile"]:
                nome_final = nome
            else:
                continue
            cercas[nome_final] = codigo
    return cercas

def extrair_patches_xml(texto):
    patches = {}
    for arq, conteudo in tag_attr_contents(texto, "editar", "arquivo"):
        arq = arq.strip()
        for a, d in re.findall(r"<<<ANTES>>>(.*?)<<<DEPOIS>>>(.*?)<<<FIM>>>", conteudo, re.DOTALL):
            patches.setdefault(arq, []).append((a.strip('\n'), d.strip('\n')))
    return patches

def aplicar_patches(conteudo, patches):
    resultados, erros = [], []
    conteudo = conteudo.replace('\r', '')
    for antes, depois in patches:
        antes  = antes.replace('\r', '')
        depois = depois.replace('\r', '')
        if antes in conteudo:
            conteudo = conteudo.replace(antes, depois, 1); resultados.append(True)
        elif antes.strip() in conteudo:
            conteudo = conteudo.replace(antes.strip(), depois.strip(), 1); resultados.append(True)
        else:
            an = re.sub(r'[ \t]+', ' ', antes.strip())
            cn = re.sub(r'[ \t]+', ' ', conteudo)
            if an in cn:
                idx = cn.index(an)
                conteudo = conteudo[:idx] + depois + conteudo[idx+len(an):]
                resultados.append(True)
            else:
                erros.append(f"Trecho não encontrado: '{antes[:60].replace(chr(10),' ')}...'")
                resultados.append(False)
    return conteudo, resultados, erros

def extrair_instalar(texto):
    ign = {"nenhum","nada","none","false","nao","não"}
    return [p.strip() for p in tag_contents(texto, "instalar")
            if p.strip().lower() not in ign and not p.strip().endswith(".js")]

def extrair_renomear(texto):
    r = tag_contents(texto, "renomear")
    if r:
        p = r[0].strip().split("|")
        if len(p) == 2: return p[0].strip(), p[1].strip()
    return None, None

def extrair_executar(texto):
    return bool(re.search(r"<executar\s*/>", texto))

def extrair_falar(texto):
    return "\n\n".join(b.strip() for b in tag_contents(texto, "falar") if b.strip())

def extrair_pensar(texto):
    return "\n\n".join(b.strip() for b in tag_contents(texto, "pensar") if b.strip())


# ── Árvore de arquivos ───────────────────────────────────────────

def arvore_json(pasta, profundidade=0, max_prof=4):
    nos = []
    try: itens = sorted(Path(pasta).iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError: return nos
    for item in itens:
        if item.name in IGNORAR or item.name.startswith('.'): continue
        if item.is_dir():
            filhos = arvore_json(item, profundidade+1, max_prof) if profundidade < max_prof else []
            nos.append({"nome": item.name, "path": str(item), "tipo": "dir", "filhos": filhos})
        else:
            nos.append({"nome": item.name, "path": str(item), "tipo": "arquivo", "tamanho": item.stat().st_size})
    return nos

def arquivo_relativo(caminho=None):
    alvo = caminho or proj["arquivo"]
    if not alvo or not proj["pasta_work"]: return alvo
    try: return os.path.relpath(alvo, proj["pasta_work"]).replace("\\", "/")
    except: return alvo


# ── Core ─────────────────────────────────────────────────────────

def abrir_seletor_windows():
    root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
    pasta = filedialog.askdirectory(title="Selecione a pasta do projeto para o Lata Velha")
    root.destroy(); return pasta

def rodar_projeto():
    global proc_ativo
    if not proj["pasta_work"]:
        log_output("[!] Nenhum projeto carregado."); return
    candidatos = []
    if proj["arquivo"] and proj["arquivo"].endswith(('.py','.js')): candidatos.append(proj["arquivo"])
    candidatos.append(os.path.join(proj["pasta_work"], proj["entrypoint"]))
    for fb in ['main.py','app.py','script.js','index.js','app.js','server.js']:
        candidatos.append(os.path.join(proj["pasta_work"], fb))
    try:
        execs = list(Path(proj["pasta_work"]).glob('*.py')) + list(Path(proj["pasta_work"]).glob('*.js'))
        if len(execs) == 1: candidatos.append(str(execs[0]))
    except: pass
    alvo = next((c for c in candidatos if os.path.exists(c)), None)
    if not alvo:
        if list(Path(proj["pasta_work"]).glob('*.html')): log_output("[OK] Projeto HTML — veja na aba Preview.")
        else: log_output("[!] Nenhum script executável encontrado.")
        return
    ext = alvo.split('.')[-1].lower()
    cmd = [sys.executable, alvo] if ext=='py' else ['node', alvo] if ext=='js' else None
    if not cmd: log_output(f"[!] Formato .{ext} não suportado."); return
    log_output(f"[RODAR] {os.path.basename(alvo)}")
    log_output("="*50)
    try:
        proc_ativo = subprocess.Popen(cmd, cwd=proj["pasta_work"],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for linha in proc_ativo.stdout: log_output(linha.rstrip())
        proc_ativo.wait()
        log_output(f"[FIM] código de saída: {proc_ativo.returncode}")
    except FileNotFoundError: log_output("[!] Interpretador não encontrado.")
    except KeyboardInterrupt:
        if proc_ativo: proc_ativo.terminate(); log_output("[INTERROMPIDO]")
    finally: proc_ativo = None

def instalar_pacote(pacote):
    log_output(f"[INSTALAR] {pacote}...")
    subprocess.run([sys.executable, "-m", "pip", "install", pacote])
    log_output(f"[OK] {pacote} instalado.")

def pasta_work_para(nome):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.abspath(os.path.join(PASTA_TEMP, f"{nome}_{ts}"))

def salvar_arquivo_com_dirs(abs_path, codigo):
    """Cria o arquivo e todos os diretórios pai necessários."""
    pai = os.path.dirname(abs_path)
    if pai:
        os.makedirs(pai, exist_ok=True)
    Path(abs_path).write_text(codigo, encoding='utf-8')

def adicionar_historico(user_msg, assistant_msg):
    proj["historico"].append({"role":"user","content":user_msg})
    proj["historico"].append({"role":"assistant","content":assistant_msg})
    if len(proj["historico"]) > 6: proj["historico"] = proj["historico"][-6:]


# ── Setup inicial do projeto ─────────────────────────────────────

def carregar_context_md(pasta):
    """Lê context.md da pasta do projeto se existir. Retorna texto ou None."""
    caminho = Path(pasta) / "context.md"
    if caminho.exists():
        try:
            return caminho.read_text(encoding='utf-8').strip()
        except:
            pass
    return None

def executar_setup(pasta_orig):
    """Carrega o projeto em memória. NÃO chama LLM — aguarda primeiro prompt do usuário."""
    context_md = carregar_context_md(pasta_orig)
    proj.update({
        "pasta_orig":  pasta_orig,
        "pasta_work":  pasta_orig,
        "arquivo":     None,
        "historico":   [],
        "setup_feito": True,
        "resumo_c1":   context_md,  # context.md vira o C1 inicial se existir
    })

    # Apenas mede o contexto para exibir na UI
    montar_contexto_inteligente(pasta_orig, None, proj["entrypoint"])

    if context_md:
        push_msg("sistema", f"[OK] context.md carregado como contexto inicial ({len(context_md)} chars).")
    log_output(f"[OK] Projeto carregado: {pasta_orig}")
    push_msg("sistema", f"[OK] Projeto pronto. Contexto: ~{proj['ctx_tokens']:,} tok ({proj['ctx_chars']//1024} KB). Aguardando instrução.")
    return True


def executar_compact():
    """Compacta o histórico de conversas em um resumo C1. C2 (código) entra automaticamente em cada prompt."""
    if not proj["pasta_work"]:
        push_msg("sistema", "[!] Nenhum projeto carregado para compactar."); return

    if not proj["historico"]:
        push_msg("sistema", "[AVISO] Histórico vazio — nada para compactar."); return

    log_output("[COMPACT] Compactando histórico...")
    push_msg("sistema", "[COMPACT] Gerando resumo do histórico...")

    # Compacta o histórico de conversas (C1)
    # C2 (código dos arquivos) entra automaticamente em cada prompt via montar_contexto_inteligente
    hist_texto = ""
    for m in proj["historico"]:
        role = "Usuário" if m["role"] == "user" else "IA"
        hist_texto += f"\n[{role}]: {m['content'][:800]}\n"

    entrada_compact = (
        f"HISTÓRICO DE CONVERSAS A RESUMIR:\n{hist_texto}\n\n"
        "Produza o resumo técnico denso do que foi feito/decidido."
    )

    msgs = [{"role": "user", "content": entrada_compact}]
    resumo = chamar_llm(SISTEMA_COMPACT, msgs)

    proj["resumo_c1"] = resumo
    proj["historico"] = []  # limpa histórico — agora está no resumo C1

    # Persistir context.md na pasta do projeto
    if proj["pasta_work"]:
        try:
            ctx_path = Path(proj["pasta_work"]) / "context.md"
            ctx_path.write_text(resumo, encoding='utf-8')
            push_msg("sistema", f"[OK] context.md atualizado em {proj['pasta_work']}")
        except Exception as e:
            log_output(f"[AVISO] Não foi possível salvar context.md: {e}")

    push_msg("sistema", f"[COMPACT OK] Histórico compactado em C1. C2 (código) entra normalmente nos próximos prompts.")
    push_msg("compact", resumo)


# ── Processamento do Prompt ──────────────────────────────────────

def processar_prompt(entrada):
    try:
        # Comando /compact
        if entrada.strip().lower() == "/compact":
            executar_compact(); return

        # Comando /entrypoint
        if entrada.startswith("/entrypoint "):
            proj["entrypoint"] = entrada[12:].strip()
            log_output(f"[OK] Entrypoint: {proj['entrypoint']}"); return

        log_output(f"[LLM] Processando: '{entrada[:60]}{'...' if len(entrada)>60 else ''}'")

        if not proj["pasta_work"]:
            texto = chamar_llm(SISTEMA_CRIAR, [{"role":"user","content":entrada}])
        else:
            ctx = montar_contexto_inteligente(proj["pasta_work"], proj["arquivo"], proj["entrypoint"])

            # Prefixar com resumo C1 se existir
            prefixo_resumo = ""
            if proj["resumo_c1"]:
                prefixo_resumo = f"## RESUMO DO CONTEXTO ANTERIOR (C1):\n{proj['resumo_c1']}\n\n---\n\n"

            msgs = proj["historico"] + [{"role":"user","content":
                f"{prefixo_resumo}{ctx}\n\nINSTRUÇÃO DO USUÁRIO: {entrada}"}]
            texto = chamar_llm(SISTEMA_EDITAR, msgs)

        # Publicar <falar>
        f = extrair_falar(texto)
        if f: push_msg("falar", f)

        # Renomear
        arq_antigo, arq_novo = extrair_renomear(texto)
        if arq_novo and proj["pasta_work"]:
            antigo = os.path.join(proj["pasta_work"], arq_antigo) if arq_antigo else proj["arquivo"]
            if antigo and os.path.exists(antigo):
                novo = os.path.join(proj["pasta_work"], arq_novo)
                try:
                    os.rename(antigo, novo)
                    log_output(f"[OK] Renomeado: {os.path.basename(antigo)} → {arq_novo}")
                    if proj["arquivo"] == antigo: proj["arquivo"] = novo
                except Exception as e: log_output(f"[!] Erro ao renomear: {e}")

        # Instalar
        for pkg in extrair_instalar(texto): instalar_pacote(pkg)

        # Criar (<codar>)
        cercas = extrair_cercas(texto)
        if not cercas and "<codar>" in texto:
            log_output("[AVISO] <codar> encontrado mas nenhum arquivo extraído — verifique formato da fence")
        primeiro_alvo = None
        for nome, codigo in cercas.items():
            pasta_dest = proj["pasta_work"] or os.getcwd()
            alvo = os.path.join(pasta_dest, nome)
            try:
                salvar_arquivo_com_dirs(alvo, codigo)
                if os.path.exists(alvo):
                    tam = os.path.getsize(alvo)
                    log_output(f"[SALVO] {nome} ({tam} bytes)")
                    push_msg("codar", f"Arquivo criado: {nome} ({tam} bytes)")
                else:
                    log_output(f"[!] Falha silenciosa ao salvar {nome} — arquivo não encontrado após escrita")
                    push_msg("sistema", f"[!] Erro ao salvar {nome}")
            except Exception as e:
                log_output(f"[!] Erro ao salvar {nome}: {e}")
                push_msg("sistema", f"[!] Erro ao criar {nome}: {e}")
            if not primeiro_alvo: primeiro_alvo = alvo

        # Editar (<editar>)
        patches = extrair_patches_xml(texto)
        for arq in list(patches.keys()):
            if arq in cercas: del patches[arq]

        for arq_alvo, lista in patches.items():
            abs_path = os.path.join(proj["pasta_work"], arq_alvo)
            if not os.path.exists(abs_path):
                salvar_arquivo_com_dirs(abs_path, "\n".join(d for _,d in lista))
                log_output(f"[CRIADO] {arq_alvo}")
                push_msg("editar", f"Arquivo criado: {arq_alvo}")
                if not primeiro_alvo: primeiro_alvo = abs_path
                continue
            codigo_atual = Path(abs_path).read_text(encoding='utf-8')
            novo_codigo, resultados, erros = aplicar_patches(codigo_atual, lista)
            for e in erros: log_output(f"  [AVISO] {arq_alvo}: {e}")
            aplicados = sum(1 for r in resultados if r)
            if aplicados > 0:
                Path(abs_path).write_text(novo_codigo, encoding='utf-8')
                log_output(f"[EDITADO] {arq_alvo} — {aplicados}/{len(lista)} blocos")
                push_msg("editar", f"{arq_alvo} — {aplicados}/{len(lista)} blocos editados")
                if not primeiro_alvo: primeiro_alvo = abs_path

        if primeiro_alvo:
            proj["arquivo"] = primeiro_alvo
            if not proj["pasta_work"]: proj["pasta_work"] = os.getcwd()

        # Executar
        if extrair_executar(texto):
            log_output("[OK] Executando projeto...")
            if not proc_ativo: threading.Thread(target=rodar_projeto, daemon=True).start()
            else: log_output("[!] Projeto já em execução.")

        # Fallback: IA não usou nenhuma tag reconhecida
        if not any(t in texto for t in ["<falar>","<codar>","<editar"]) and texto.strip():
            push_msg("falar", texto.strip())

        adicionar_historico(entrada, texto)

    except Exception as e:
        import traceback
        log_output(f"[!] Erro crítico: {e}")
        log_output(traceback.format_exc())


def chamar_llm(sistema, mensagens):
    payload = {"model": MODELO,
               "messages": [{"role":"system","content":sistema}] + mensagens,
               "stream": True, "temperature": 0.1}
    resp = requests.post(URL, json=payload, stream=True)
    resp.raise_for_status()
    texto = ""; sessao_t = False; sessao_c = False
    tokens_gerados = 0
    t_inicio = None
    ultimo_push_tok = 0  # para não spammar o buffer

    for line in resp.iter_lines():
        if not line: continue
        decoded = line.decode('utf-8')
        if not decoded.startswith("data: "): continue
        raw = decoded[6:]
        if raw.strip() == "[DONE]": break
        try:
            delta = json.loads(raw)['choices'][0]['delta']
            thinking = delta.get('reasoning_content') or delta.get('reasoning')
            if thinking:
                if not sessao_t: print("\n"+"="*20+" THINKING "+"="*20); sessao_t=True
                sys.stdout.write(thinking); sys.stdout.flush(); continue
            content = delta.get('content')
            if content:
                if not sessao_c:
                    print("\n"+"="*20+" STREAMING "+"="*20)
                    sessao_c = True
                    t_inicio = time.time()
                sys.stdout.write(content); sys.stdout.flush()
                texto += content
                tokens_gerados += len(content) // 4  # estimativa

                # Emitir update de tokens a cada ~50 tokens novos
                if tokens_gerados - ultimo_push_tok >= 50:
                    ultimo_push_tok = tokens_gerados
                    elapsed = time.time() - t_inicio if t_inicio else 0
                    tps = tokens_gerados / elapsed if elapsed > 0.1 else 0
                    proj["ctx_tokens_streaming"] = tokens_gerados
                    push_msg("ctx_update", json.dumps({
                        "tokens_novos": tokens_gerados,
                        "tps": round(tps, 1),
                        "elapsed": round(elapsed, 1)
                    }))
        except: continue

    print("\n"+"="*50)

    # Calcular e publicar tokens/s finais
    if t_inicio and tokens_gerados > 0:
        elapsed = time.time() - t_inicio
        tps = tokens_gerados / elapsed if elapsed > 0 else 0
        info_tps = f"~{tokens_gerados} tokens em {elapsed:.1f}s ({tps:.1f} tok/s)"
        log_output(f"[TPS] {info_tps}")
        push_msg("tps", info_tps)

    return texto


# ── Servidor HTTP ────────────────────────────────────────────────

class UIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def responder_json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(corpo))
        self.end_headers(); self.wfile.write(corpo)

    def responder_html(self, html):
        corpo = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(corpo))
        self.end_headers(); self.wfile.write(corpo)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs     = urllib.parse.parse_qs(parsed.query)
        path   = parsed.path

        if path == "/":
            html_path = os.path.join(DIR_SCRIPT, "interface.html")
            if os.path.exists(html_path):
                with open(html_path, encoding="utf-8") as f: self.responder_html(f.read())
            else: self.responder_html("<h2>interface.html não encontrado</h2>")

        elif path == "/api/estado":
            self.responder_json({
                "pasta_orig":  proj["pasta_orig"],
                "pasta_work":  proj["pasta_work"],
                "arquivo":     proj["arquivo"],
                "entrypoint":  proj["entrypoint"],
                "rodando":     proc_ativo is not None,
                "setup_feito": proj["setup_feito"],
                "tem_resumo":  proj["resumo_c1"] is not None,
                "ctx_tokens":  proj["ctx_tokens"],
                "ctx_chars":   proj["ctx_chars"],
            })

        elif path == "/api/arvore":
            pasta = proj["pasta_work"]
            self.responder_json(arvore_json(pasta) if pasta and os.path.isdir(pasta) else [])

        elif path == "/api/arquivo":
            caminho = qs.get("path",[None])[0]
            if caminho and os.path.isfile(caminho):
                conteudo = Path(caminho).read_text(encoding='utf-8', errors='replace')
                rel = os.path.relpath(caminho, proj["pasta_work"]).replace("\\","/") if proj["pasta_work"] else ""
                self.responder_json({"path":caminho,"rel_path":rel,"conteudo":conteudo})
            else: self.responder_json({"erro":"arquivo não encontrado"},404)

        elif path == "/api/msgs":
            desde = int(qs.get("desde",["0"])[0])
            with msg_lock:
                msgs  = msg_buffer[desde:]
                total = len(msg_buffer)
            self.responder_json({"msgs":msgs,"total":total})

        elif path == "/api/output":
            desde = int(qs.get("desde",["0"])[0])
            with output_lock:
                linhas = output_buffer[desde:]
                total  = len(output_buffer)
            self.responder_json({"linhas":linhas,"total":total})

        elif path == "/api/layout":
            layout_path = os.path.join(DIR_SCRIPT, "layout.json")
            if os.path.isfile(layout_path):
                try:
                    dados = json.loads(Path(layout_path).read_text(encoding='utf-8'))
                    self.responder_json(dados)
                except:
                    self.responder_json({})
            else:
                self.responder_json({})

        elif path == "/api/escolher_pasta":
            pasta = abrir_seletor_windows()
            if pasta:
                # Setup obrigatório: carrega tudo e espera LLM analisar
                threading.Thread(target=executar_setup, args=(pasta,), daemon=True).start()
                self.responder_json({"ok":True,"pasta":pasta,"msg":"Setup iniciado..."})
            else: self.responder_json({"ok":False,"erro":"Nenhuma pasta selecionada."})

        elif not path.startswith("/api/"):
            if proj["pasta_work"]:
                rel   = urllib.parse.unquote(path.lstrip('/'))
                cam   = os.path.abspath(os.path.join(proj["pasta_work"], rel))
                if cam.startswith(os.path.abspath(proj["pasta_work"])) and os.path.isfile(cam):
                    ct, _ = mimetypes.guess_type(cam)
                    ct = ct or 'application/octet-stream'
                    if ct.startswith('text/') or ct in ['application/javascript','application/json']: ct += '; charset=utf-8'
                    try:
                        corpo = Path(cam).read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", ct)
                        self.send_header("Access-Control-Allow-Origin","*")
                        self.send_header("Cache-Control","no-store")
                        self.send_header("Content-Length",len(corpo))
                        self.end_headers(); self.wfile.write(corpo); return
                    except: pass
            self.send_response(404); self.end_headers()
        else: self.send_response(404); self.end_headers()

    def do_POST(self):
        parsed  = urllib.parse.urlparse(self.path)
        path    = parsed.path
        tamanho = int(self.headers.get("Content-Length",0))
        corpo   = json.loads(self.rfile.read(tamanho)) if tamanho else {}

        if path == "/api/abrir":
            cam = corpo.get("path","")
            if os.path.isfile(cam):
                proj["arquivo"]=cam; proj["historico"]=[]
                self.responder_json({"ok":True,"arquivo":cam})
            else: self.responder_json({"ok":False,"erro":"não encontrado"},404)

        elif path == "/api/prompt":
            prompt = corpo.get("prompt","").strip()
            if not proj["setup_feito"] and proj["pasta_work"]:
                self.responder_json({"ok":False,"erro":"Setup ainda em andamento. Aguarde."})
                return
            if prompt: threading.Thread(target=processar_prompt,args=(prompt,),daemon=True).start()
            self.responder_json({"ok":True})

        elif path == "/api/rodar":
            if proc_ativo: self.responder_json({"ok":False,"erro":"já rodando"})
            else:
                threading.Thread(target=rodar_projeto,daemon=True).start()
                self.responder_json({"ok":True})

        elif path == "/api/layout":
            layout_path = os.path.join(DIR_SCRIPT, "layout.json")
            try:
                Path(layout_path).write_text(json.dumps(corpo, ensure_ascii=False), encoding='utf-8')
                self.responder_json({"ok": True})
            except Exception as e:
                self.responder_json({"ok": False, "erro": str(e)})

        elif path == "/api/parar":
            if proc_ativo: proc_ativo.terminate(); self.responder_json({"ok":True})
            else: self.responder_json({"ok":False,"erro":"nenhum processo ativo"})

        else: self.send_response(404); self.end_headers()


class ServidorResiliente(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads      = True

def iniciar_servidor():
    try:
        s = ServidorResiliente(("localhost", PORTA_UI), UIHandler)
        print(f"--- Servidor Web Ativo ---")
        print(f"Abra no navegador: http://localhost:{PORTA_UI}")
        s.serve_forever()
    except OSError as e:
        print(f"\n[!] ERRO ao abrir servidor: {e}")

if __name__ == "__main__":
    iniciar_servidor()
