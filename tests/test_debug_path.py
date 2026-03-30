def test_show_path():
    import sys
    print("\n sys.path:", sys.path)
    import os
    print("cwd:", os.getcwd())
    # Try to list what's in cwd
    print("cwd contents:", os.listdir('.'))
    try:
        import src
        print("import src: OK")
    except Exception as e:
        print(f"import src failed: {e}")
