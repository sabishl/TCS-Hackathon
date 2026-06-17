import os
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "local")

def get_llm(groq_api_key: str = None):
    """Return LLM instance depending on environment."""
    if ENV == "local":
        from langchain_groq import ChatGroq
        api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment or session state.")
        return ChatGroq(
            api_key=api_key,
            model="llama3-8b-8192",
            temperature=0
        )
    else:
        # AMD Cloud — vLLM serving LLaMA on MI300X via ROCm
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            from langchain_community.chat_models.openai import ChatOpenAI
            
        return ChatOpenAI(
            base_url="http://localhost:8000/v1",
            api_key="EMPTY",
            model="meta-llama/Llama-3.1-8B-Instruct",
            temperature=0
        )

def get_embeddings():
    """Return embedding model instance depending on environment."""
    if ENV == "groq":
        # Local CPU embeddings for Groq cloud fallback
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    else:
        # Both "local" (Ollama local) and "amd_cloud" (Ollama ROCm) use Ollama nomic-embed-text
        from langchain_community.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(model="nomic-embed-text")

def get_system_metrics():
    """Retrieve system CPU, RAM and GPU metrics dynamically."""
    import psutil
    import subprocess
    import shutil
    
    metrics = {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "ram_pct": psutil.virtual_memory().percent,
        "gpu_name": None,
        "gpu_pct": None,
        "vram_pct": None,
        "raw_gpu": ""
    }
    
    # Try AMD ROCm GPU
    if shutil.which("rocm-smi"):
        try:
            res = subprocess.run(["rocm-smi"], capture_output=True, text=True, timeout=1.5)
            lines = res.stdout.splitlines()
            for line in lines:
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    if len(parts) >= 10:
                        vram = parts[-2].replace("%", "")
                        gpu_use = parts[-1].replace("%", "")
                        metrics["gpu_name"] = "AMD Instinct GPU"
                        metrics["gpu_pct"] = float(gpu_use) if gpu_use.isdigit() else 0.0
                        metrics["vram_pct"] = float(vram) if vram.isdigit() else 0.0
                        metrics["raw_gpu"] = res.stdout
                        break
        except Exception:
            pass
            
    # Try NVIDIA GPU
    elif shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,utilization.memory", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1.5)
            parts = res.stdout.strip().split(",")
            if len(parts) >= 3:
                metrics["gpu_name"] = parts[0].strip()
                metrics["gpu_pct"] = float(parts[1].strip())
                metrics["vram_pct"] = float(parts[2].strip())
        except Exception:
            pass
            
    return metrics

