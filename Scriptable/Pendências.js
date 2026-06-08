// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: teal; icon-glyph: magic;
// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: deep-purple; icon-glyph: handshake;

const BASE_URL = "https://script.google.com/macros/s/AKfycbw1LZ-0o_KJ_7bzim98xSRp7fEzCAbvxdhsRUIdSYEzzop7LQW1fOXSFFQGCFBBHyM/exec";

async function fetchJSON(url) {
  const req = new Request(url);
  return await req.loadJSON();
}

function parseValorBR(v) {
  if (v === null || v === undefined) return null;

  let texto = String(v).trim();

  // Remove R$, espaços e outros caracteres comuns
  texto = texto.replace(/[R$\s]/g, "");

  // Caso venha como 1.234,56
  if (texto.includes(",") && texto.includes(".")) {
    texto = texto.replace(/\./g, "").replace(",", ".");
  }
  // Caso venha como 1234,56
  else if (texto.includes(",")) {
    texto = texto.replace(",", ".");
  }

  const n = Number(texto);
  return Number.isFinite(n) ? n : null;
}

function extrairSaldo(p1) {
  if (p1 === null || p1 === undefined) return null;

  // Caso o retorno seja direto: "1200,00" ou 1200
  if (typeof p1 === "string" || typeof p1 === "number") {
    return parseValorBR(p1);
  }

  // Seu BASE_URL retorna um array de objetos
  if (Array.isArray(p1)) {
    // Procura a linha marcada como SALDO_FIXO
    const linhaSaldo = p1.find(item =>
      item &&
      String(item["Indicador"]).trim().toUpperCase() === "SALDO_FIXO"
    );

    if (linhaSaldo && linhaSaldo["Saldo atual"] !== undefined && linhaSaldo["Saldo atual"] !== "") {
      return parseValorBR(linhaSaldo["Saldo atual"]);
    }

    // Fallback: caso a linha não tenha Indicador, tenta pegar qualquer "Saldo atual" preenchido
    for (const item of p1) {
      if (item && item["Saldo atual"] !== undefined && item["Saldo atual"] !== "") {
        const saldo = parseValorBR(item["Saldo atual"]);
        if (saldo !== null) return saldo;
      }
    }

    return null;
  }

  // Caso algum dia o Apps Script volte a retornar objeto único
  if (typeof p1 === "object") {
    const possiveisChaves = [
      "saldoFixo",
      "saldo",
      "Saldo",
      "SALDO",
      "saldoAtual",
      "saldo_atual",
      "Saldo atual",
      "valor",
      "Valor"
    ];

    for (const chave of possiveisChaves) {
      if (p1[chave] !== undefined && p1[chave] !== "") {
        const saldo = parseValorBR(p1[chave]);
        if (saldo !== null) return saldo;
      }
    }
  }

  return null;
}

function parseLinha(linha) {
  const texto = String(linha).trim();

  let m = texto.match(/^(.+?)\s+te deve\s+R\$\s*([\d.,]+)/i);
  if (m) {
    return {
      nome: m[1].trim(),
      valor: parseValorBR(m[2]),
      tipo: "receber"
    };
  }

  m = texto.match(/você deve\s+R\$\s*([\d.,]+)\s+para\s+(.+)/i);
  if (m) {
    return {
      nome: m[2].trim(),
      valor: parseValorBR(m[1]),
      tipo: "pagar"
    };
  }

  return null;
}

function fmt(v) {
  return v.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

async function createWidget() {
  let saldoAtual = null;
  let dividas = [];
  let erroSaldo = false;

  // Busca saldo atual
  try {
    const p1 = await fetchJSON(BASE_URL);
    saldoAtual = extrairSaldo(p1);

    if (saldoAtual === null) {
      erroSaldo = true;
    }
  } catch (e) {
    erroSaldo = true;
  }

  // Busca dívidas da Página2
  try {
    const p2 = await fetchJSON(BASE_URL + "?sheet=Página2");

    if (Array.isArray(p2)) {
      p2.forEach(l => {
        const p = parseLinha(l);

        if (p && p.valor !== null) {
          dividas.push(p);
        }
      });
    }
  } catch (e) {}

  const totalReceber = dividas
    .filter(d => d.tipo === "receber")
    .reduce((s, d) => s + d.valor, 0);

  const totalPagar = dividas
    .filter(d => d.tipo === "pagar")
    .reduce((s, d) => s + d.valor, 0);

  const projecao = saldoAtual !== null
    ? saldoAtual + totalReceber - totalPagar
    : null;

  let w = new ListWidget();
  w.backgroundColor = new Color("#1c1c1e");
  w.setPadding(10, 12, 10, 12);

  // Cabeçalho
  let headerStack = w.addStack();
  headerStack.layoutHorizontally();

  let titulo = headerStack.addText("DÍVIDAS");
  titulo.font = Font.systemFont(8);
  titulo.textColor = new Color("#ffffff", 0.45);

  headerStack.addSpacer();

  let leg = headerStack.addText("+ recebo  − pago");
  leg.font = Font.systemFont(7);
  leg.textColor = new Color("#ffffff", 0.3);

  w.addSpacer(5);

  // Dívidas visíveis
  const dividasVisiveis = dividas.slice(0, 4);

  if (dividas.length === 0) {
    let vazio = w.addText("Nenhuma dívida");
    vazio.font = Font.systemFont(9);
    vazio.textColor = new Color("#ffffff", 0.4);
  } else {
    dividasVisiveis.forEach(d => {
      let s = w.addStack();
      s.layoutHorizontally();

      let n = s.addText(d.nome);
      n.font = Font.systemFont(9);
      n.textColor = new Color("#ffffff", 0.85);
      n.lineLimit = 1;

      s.addSpacer();

      const sinal = d.tipo === "receber" ? "+" : "−";
      const cor = d.tipo === "receber"
        ? new Color("#32d74b")
        : new Color("#ff453a");

      let v = s.addText(`${sinal} R$${fmt(d.valor)}`);
      v.font = Font.boldSystemFont(9);
      v.textColor = cor;

      w.addSpacer(2);
    });

    if (dividas.length > 4) {
      let mais = w.addText(`+ ${dividas.length - 4} dívida(s)`);
      mais.font = Font.systemFont(7);
      mais.textColor = new Color("#ffffff", 0.35);
    }
  }

  w.addSpacer(5);

  // Saldo atual
  if (saldoAtual !== null) {
    let ss = w.addStack();
    ss.layoutHorizontally();

    let st = ss.addText("Saldo");
    st.font = Font.systemFont(8);
    st.textColor = new Color("#ffffff", 0.4);

    ss.addSpacer();

    let sv = ss.addText(`R$${fmt(saldoAtual)}`);
    sv.font = Font.boldSystemFont(9);
    sv.textColor = new Color("#ffffff", 0.7);
  }

  // Projeção
  if (projecao !== null) {
    let ps = w.addStack();
    ps.layoutHorizontally();

    let pt = ps.addText("Projeção");
    pt.font = Font.systemFont(8);
    pt.textColor = new Color("#ffffff", 0.4);

    ps.addSpacer();

    const corP = projecao >= saldoAtual
      ? new Color("#32d74b")
      : new Color("#ff453a");

    let pv = ps.addText(`R$${fmt(projecao)}`);
    pv.font = Font.boldSystemFont(9);
    pv.textColor = corP;
  } else if (erroSaldo) {
    let erro = w.addText("Saldo não encontrado");
    erro.font = Font.systemFont(8);
    erro.textColor = new Color("#ff453a");
  }

  return w;
}

let widget = await createWidget();

if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  widget.presentSmall();
}

Script.complete();