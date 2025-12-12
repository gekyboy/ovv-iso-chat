"""
OVV ISO Chat v3.1 - Mesop UI (POC)
POC minimal per testare Mesop
"""

import mesop as me

from src.ui.mesop_handlers import handle_query_poc


@me.page(path="/")
def home_page():
    """POC page semplice"""
    me.text("OVV ISO Chat v3.1 - Mesop POC", style=me.Style(font_size=24, font_weight="bold"))

    # Input semplice
    me.input(
        label="Domanda:",
        on_input=on_input_change,
        style=me.Style(width="100%", margin=me.Margin(bottom=10))
    )

    me.button("Invia Query", on_click=on_submit_query)

    # Risultato
    result = me.state().get("result", "")
    if result:
        me.text(f"Risposta: {result}", style=me.Style(margin=me.Margin(top=20)))


def on_input_change(e: me.InputEvent):
    """Salva input utente"""
    me.state(query=e.value)


def on_submit_query(e: me.ClickEvent):
    """Gestisce submit query"""
    query = me.state().get("query", "")
    if not query:
        me.state(result="Inserisci una domanda!")
        return

    try:
        # Chiama handler POC
        result = handle_query_poc(query)
        me.state(result=result)
    except Exception as ex:
        me.state(result=f"Errore: {str(ex)}")
