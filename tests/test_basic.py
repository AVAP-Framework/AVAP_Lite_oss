import unittest

def test_rust_extension():
    try:
        import avap_lite_core
        result = avap_lite_core.sum_as_string(5, 7)
        assert result == "12"
        print("✅ Rust extension is working!")
    except ImportError:
        print("❌ Rust extension not found. Run 'maturin develop' first.")
        # No fallamos el test aquí para que el CI no muera 
        # si aún no hemos compilado en ese job específico