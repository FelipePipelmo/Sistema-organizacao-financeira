// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: gray; icon-glyph: magic;
// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: green; icon-glyph: bullseye;


//  CONFIGURAÇÃO
const META_MENSAL = 2000.00; // Limite de gastos do mês em R$
const url = "https://script.google.com/macros/s/AKfycbw1LZ-0o_KJ_7bzim98xSRp7fEzCAbvxdhsRUIdSYEzzop7LQW1fOXSFFQGCFBBHyM/exec";


async function createWidget() {
  let data;
  try {
    data = await new Request(url).loadJSON();
  } catch (e) {
    let errorWidget = new ListWidget();
    errorWidget.backgroundColor = new Color("#1c1c1e");
    let errText = errorWidget.addText("Erro ao carregar");
    errText.textColor = Color.red();
    errText.font = Font.systemFont(12);
    return errorWidget;
  }

  // Filtrar gastos do mês atual
  let hoje = new Date();
  let mesAtual = (hoje.getMonth() + 1).toString().padStart(2, '0');
  let anoAtual = hoje.getFullYear().toString();

  let gastosMes = 0;

  data.forEach(row => {
    let valorStr = String(row["Valor"]).replace(",", ".");
    let dataTexto = String(row["Data"] || "");
    let valor = parseFloat(valorStr);

    // Apenas saídas (valores negativos) do mês/ano atual
    if (!isNaN(valor) && valor < 0) {
      // Data no formato DD/MM/YYYY
      let partes = dataTexto.split("/");
      if (partes.length >= 3) {
        let mesDado = partes[1];
        let anoDado = partes[2].substring(0, 4);
        if (mesDado === mesAtual && anoDado === anoAtual) {
          gastosMes += Math.abs(valor);
        }
      }
    }
  });

  let percentual = Math.min(gastosMes / META_MENSAL, 1.0); // 0.0 a 1.0
  let percentualTexto = Math.round(percentual * 100);
  let restante = META_MENSAL - gastosMes;

  // Define cor conforme progresso
  let corBarra;
  let corValor;
  if (percentual < 0.6) {
    corBarra = new Color("#32d74b"); // Verde
    corValor = new Color("#32d74b");
  } else if (percentual < 0.85) {
    corBarra = new Color("#ffd60a"); // Amarelo
    corValor = new Color("#ffd60a");
  } else {
    corBarra = new Color("#ff453a"); // Vermelho
    corValor = new Color("#ff453a");
  }


  // Monta o widget pequeno
  let w = new ListWidget();
  w.backgroundColor = new Color("#1c1c1e");
  w.setPadding(12, 14, 10, 14);

  // Título
  let titulo = w.addText("META DO MÊS");
  titulo.font = Font.systemFont(9);
  titulo.textColor = new Color("#ffffff", 0.5);

  w.addSpacer(4);

  // Valor gasto
  let gastoLabel = w.addText(`R$ ${gastosMes.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);
  gastoLabel.font = Font.boldSystemFont(15);
  gastoLabel.textColor = corValor;

  w.addSpacer(2);

  // Meta total
  let metaLabel = w.addText(`de R$ ${META_MENSAL.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);
  metaLabel.font = Font.systemFont(9);
  metaLabel.textColor = new Color("#ffffff", 0.45);

  w.addSpacer(7);

  // Barra de progresso
  const TOTAL_BLOCOS = 14;
  let blocosPreenchidos = Math.round(percentual * TOTAL_BLOCOS);
  let blocosVazios = TOTAL_BLOCOS - blocosPreenchidos;
  let barraTexto = "█".repeat(blocosPreenchidos) + "░".repeat(blocosVazios);

  let barra = w.addText(barraTexto);
  barra.font = Font.systemFont(9);
  barra.textColor = corBarra;

  w.addSpacer(4);

  // Linha inferior: percentual + restante
  let infoStack = w.addStack();
  infoStack.layoutHorizontally();

  let pctText = infoStack.addText(`${percentualTexto}% usado`);
  pctText.font = Font.systemFont(8);
  pctText.textColor = new Color("#ffffff", 0.4);

  infoStack.addSpacer();

  let restLabel = infoStack.addText(
    restante >= 0
      ? `sobra R$ ${restante.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`
      : `excedeu R$ ${Math.abs(restante).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`
  );
  restLabel.font = Font.systemFont(8);
  restLabel.textColor = restante >= 0 ? new Color("#ffffff", 0.4) : new Color("#ff453a");

  return w;
}

let widget = await createWidget();
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  widget.presentSmall(); // Prévia em tamanho pequeno
}
Script.complete();