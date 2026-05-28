// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: brown; icon-glyph: magic;
const url = "https://script.google.com/macros/s/AKfycbw1LZ-0o_KJ_7bzim98xSRp7fEzCAbvxdhsRUIdSYEzzop7LQW1fOXSFFQGCFBBHyM/exec";

async function createWidget() {
  let data;
  try {
    data = await new Request(url).loadJSON();
  } catch (e) {
    let errorWidget = new ListWidget();
    errorWidget.addText("Erro ao conectar na planilha");
    return errorWidget;
  }
  
  let w = new ListWidget();
  w.backgroundColor = new Color("#1c1c1e");
  w.setPadding(10, 15, 10, 10);

  // Título
  let title = w.addText("My balance");
  title.font = Font.boldSystemFont(16);
  title.textColor = Color.white();
  w.addSpacer(8); 

  // Filtro de segurança
  let cleanData = data.filter(row => {
    let desc = row["Descrição"];
    let val = String(row["Valor"]);
    return desc && desc.trim() !== "" && !val.includes("T03:00");
  });

  for (let i = 0; i < Math.min(cleanData.length, 15); i++) {
    let row = cleanData[i];
    let rowStack = w.addStack();
    rowStack.centerAlignContent(); // Alinha verticalmente os textos na linha
    
    let descText = rowStack.addText(`• ${row["Descrição"]}: `);
    descText.font = Font.systemFont(12);
    descText.textColor = new Color("#ffffff", 0.9);
    descText.lineLimit = 1;

    // --- LÓGICA DE CORES ---
    let valorStr = String(row["Valor"]);
    let valText = rowStack.addText(`R$ ${valorStr}`);
    valText.font = Font.boldSystemFont(12);

    if (valorStr.startsWith("-")) {
      valText.textColor = Color.red(); // Vermelho para negativos
    } else {
      valText.textColor = Color.green(); // Verde para positivos/neutros
    }
    // -----------------------
    
    w.addSpacer(4); 
  }

  return w;
}

let widget = await createWidget();
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  widget.presentLarge();
}
Script.complete();