#!/usr/bin/env python3
import sys, os, re, importlib

# Ensure project root in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

def check(condition, message):
    if condition:
        print(f"[PASS] {message}")
        return True
    else:
        print(f"[FAIL] {message}")
        return False

all_pass = True

# 1. Check system.py source does not import MemoryManager
with open('src/core/system.py', 'r') as f:
    system_src = f.read()
all_pass &= check(
    'from src.memory.manager import' not in system_src,
    "system.py does not import MemoryManager"
)
all_pass &= check(
    'self.memory = MemoryManager()' not in system_src,
    "system.py does not instantiate MemoryManager"
)

# 2. Check retriever.py does not define HybridRetriever
with open('src/research/reasoning/retriever.py', 'r') as f:
    retriever_src = f.read()
all_pass &= check(
    'class HybridRetriever' not in retriever_src,
    "retriever.py: HybridRetriever class removed"
)

# 3. Check that system module does not expose MemoryManager
try:
    system_mod = importlib.import_module('src.core.system')
    all_pass &= check(
        'MemoryManager' not in dir(system_mod),
        "system module does not reference MemoryManager"
    )
    # Instantiate SystemManager and check memory attribute
    sm = system_mod.SystemManager()
    all_pass &= check(
        sm.memory is None,
        "SystemManager().memory is None (V2 removed)"
    )
    # Check that retriever type hint is V3Retriever (class-level attribute not set until init)
    # We can check that the class uses V3Retriever in its __init__
    import inspect
    init_src = inspect.getsource(sm.__init__)
    all_pass &= check(
        'V3Retriever' in init_src,
        "SystemManager.__init__ references V3Retriever"
    )
except Exception as e:
    print(f"[FAIL] Import/instantiation error: {e}")
    all_pass = False

# 4. Ensure pipeline does not import MemoryManager
with open('src/research/condensation/pipeline.py', 'r') as f:
    pipeline_src = f.read()
all_pass &= check(
    'from src.memory.manager import' not in pipeline_src,
    "pipeline.py does not import MemoryManager"
)

# 5. Ensure synthesis_service does not import MemoryManager
with open('src/research/reasoning/synthesis_service.py', 'r') as f:
    synth_src = f.read()
all_pass &= check(
    'from src.memory.manager import' not in synth_src,
    "synthesis_service.py does not import MemoryManager"
)

# 6. Ensure memory_integration does not import MemoryManager at top level
with open('src/research/memory_integration.py', 'r') as f:
    memint_src = f.read()
all_pass &= check(
    not re.search(r'from src\.memory\.manager import', memint_src),
    "memory_integration.py does not import MemoryManager at top level"
)

print("\n" + "="*60)
if all_pass:
    print("PHASE 03.0 VERIFICATION: PASS")
    sys.exit(0)
else:
    print("PHASE 03.0 VERIFICATION: FAIL")
    sys.exit(1)
