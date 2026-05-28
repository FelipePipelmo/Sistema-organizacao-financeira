// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: purple; icon-glyph: magic;
const url = "https://script.google.com/macros/s/AKfycbw1LZ-0o_KJ_7bzim98xSRp7fEzCAbvxdhsRUIdSYEzzop7LQW1fOXSFFQGCFBBHyM/exec";



async function createWidget() {

  let data;

  try {

    data = await new Request(url).loadJSON();

  } catch (e) {

    let errorWidget = new ListWidget();

    errorWidget.addText("Erro ao carregar");

    return errorWidget;

  }



  let saldoExibir = 0;

  let entradasHoje = 0;

  let saidasHoje = 0;

  

  let hojeObj = new Date();

  let dia = hojeObj.getDate().toString().padStart(2, '0');

  let mes = (hojeObj.getMonth() + 1).toString().padStart(2, '0');

  let ano = hojeObj.getFullYear();

  const hojeString = `${dia}/${mes}/${ano}`;



  if (data.length > 0 && data[0]["Saldo atual"] !== undefined) {

    saldoExibir = parseFloat(String(data[0]["Saldo atual"]).replace(",", "."));

  }



  data.forEach(row => {

    let valor = parseFloat(String(row["Valor"]).replace(",", "."));

    let dataTexto = String(row["Data"]); 

    

    if (!isNaN(valor) && dataTexto.startsWith(hojeString)) {

      if (valor > 0) {

        entradasHoje += valor;

      } else if (valor < 0) {

        saidasHoje += valor;

      }

    }

  });



  let w = new ListWidget();

  w.backgroundColor = new Color("#1c1c1e");

  w.setPadding(10, 12, 10, 12);



  // --- BLOCO FIXO: SALDO ---

  let labelSaldo = w.addText("SALDO");

  labelSaldo.font = Font.systemFont(10);

  labelSaldo.textColor = new Color("#ffffff", 0.6);

  

  let valSaldo = w.addText(`R$ ${saldoExibir.toLocaleString('pt-BR', {minimumFractionDigits: 2})}`);

  valSaldo.font = Font.boldSystemFont(14);

  valSaldo.textColor = saldoExibir >= 0 ? Color.green() : Color.red();



  w.addSpacer(6);



  // --- LÓGICA DE ORDENAÇÃO (ENTRADA VS SAÍDA) ---

  let absSaida = Math.abs(saidasHoje);

  let itens = [

    { label: "ENTRADA", valor: entradasHoje, cor: Color.cyan() },

    { label: "SAÍDA", valor: absSaida, cor: Color.orange() }

  ];



  // Ordena para que o maior valor absoluto fique em cima

  itens.sort((a, b) => b.valor - a.valor);



  // Renderiza os itens ordenados

  itens.forEach((item, index) => {

    let lbl = w.addText(item.label);

    lbl.font = Font.systemFont(9);

    lbl.textColor = new Color("#ffffff", 0.6);



    let val = w.addText(`R$ ${item.valor.toLocaleString('pt-BR', {minimumFractionDigits: 2})}`);

    val.font = Font.boldSystemFont(14);

    val.textColor = item.cor;



    if (index === 0) w.addSpacer(6); // Espaço apenas entre o primeiro e o segundo item

  });



  // Rodapé

  w.addSpacer(4);

  let timeText = w.addText(`${hojeObj.getHours()}:${hojeObj.getMinutes().toString().padStart(2, '0')}`);

  timeText.font = Font.systemFont(8);

  timeText.textColor = new Color("#ffffff", 0.2);

  timeText.rightAlignText();



  return w;

}



let widget = await createWidget();

if (config.runsInWidget) {

  Script.setWidget(widget);

} else {

  widget.presentSmall();

}

Script.complete();