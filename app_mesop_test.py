"""
Test Mesop Semplificato
"""

import mesop as me

@me.page(path="/")
def test_page():
    me.text("Test Mesop Semplificato", style=me.Style(font_size=24))
    me.text("Se vedi questo messaggio, Mesop funziona!")

    me.input(label="Test input", on_input=lambda e: me.state(test_value=e.value))
    me.button("Test button", on_click=lambda e: me.snackbar("Button clicked!"))

    value = me.state().get("test_value", "")
    if value:
        me.text(f"Input value: {value}")

if __name__ == "__main__":
    import mesop.bin as mesop_bin
    mesop_bin.main()
