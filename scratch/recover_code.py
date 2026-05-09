import os
from nexus.memory.manager import MemoryManager

def extract_code():
    memory = MemoryManager(persist_dir=".nexus/memory")
    # Search for development results in code_patterns or reflections
    memories = memory.recall("todo list", collections=["code_patterns", "reflections"], n_results=10)
    
    for mem in memories:
        print(f"--- Memory from {mem.metadata.get('source')} ---")
        print(mem.content[:500] + "...")
        if "html" in mem.content.lower() or "<!DOCTYPE html>" in mem.content:
            with open("recovered_todo_list.html", "w", encoding="utf-8") as f:
                f.write(mem.content)
            print("\n[SUCCESS] Recovered code to recovered_todo_list.html")
            return

if __name__ == "__main__":
    extract_code()
