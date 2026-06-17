import os
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "local")

def get_llm(groq_api_key: str = None):
    """Return LLM instance depending on environment."""
    if ENV == "local":
        # Local Ollama LLaMA 3.1 8B
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            model="llama3.1:8b",
            temperature=0
        )
    elif ENV == "groq":
        from langchain_groq import ChatGroq
        api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment or session state.")
        return ChatGroq(
            api_key=api_key,
            model="llama-3.1-8b-instant",
            temperature=0
        )
    else:
        # AMD Cloud — vLLM serving LLaMA on MI300X via ROCm
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://127.0.0.1:8000/v1",
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
        return OllamaEmbeddings(
            base_url="http://127.0.0.1:11434",
            model="nomic-embed-text"
        )

def get_system_metrics():
    """Retrieve system CPU, RAM, GPU, and LLaMA process metrics dynamically."""
    import psutil
    import subprocess
    import shutil
    import os
    
    metrics = {
        "cpu_pct": psutil.cpu_percent(interval=0.1),
        "ram_pct": psutil.virtual_memory().percent,
        "gpu_name": None,
        "gpu_pct": None,
        "vram_pct": None,
        "raw_gpu": "",
        "llama_cpu": 0.0,
        "llama_ram_gb": 0.0
    }
    
    # Track LLaMA/Ollama process usage (e.g. ollama.exe, llama-server.exe)
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        try:
            pname = proc.info['name'].lower()
            if 'ollama' in pname or 'llama' in pname:
                metrics["llama_cpu"] += proc.info['cpu_percent'] or 0.0
                metrics["llama_ram_gb"] += (proc.info['memory_info'].rss or 0) / (1024 * 1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    metrics["llama_ram_gb"] = round(metrics["llama_ram_gb"], 2)
    metrics["llama_cpu"] = round(metrics["llama_cpu"], 1)
    
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
            
    # Try NVIDIA GPU (checking standard PATH and common Windows installations)
    else:
        nvidia_smi_path = shutil.which("nvidia-smi") or r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
        if os.path.exists(nvidia_smi_path):
            try:
                res = subprocess.run([nvidia_smi_path, "--query-gpu=name,utilization.gpu,utilization.memory", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1.5)
                parts = res.stdout.strip().split(",")
                if len(parts) >= 3:
                    metrics["gpu_name"] = parts[0].strip()
                    metrics["gpu_pct"] = float(parts[1].strip())
                    metrics["vram_pct"] = float(parts[2].strip())
            except Exception:
                pass
                
        # Fallback for Windows Intel/AMD/NVIDIA GPU when specialized smi commands are missing
        if not metrics["gpu_name"] and os.name == 'nt':
            try:
                # Query GPU Name using PowerShell CIM
                cmd_name = "powershell -Command \"Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name\""
                res_name = subprocess.run(cmd_name, shell=True, capture_output=True, text=True, timeout=1.5)
                if res_name.returncode == 0 and res_name.stdout.strip():
                    metrics["gpu_name"] = res_name.stdout.strip().splitlines()[0]
                    
                # Query GPU utilization
                cmd_util = "powershell -Command \"Get-CimInstance -Query 'SELECT UtilizationPercentage FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine' | Measure-Object -Property UtilizationPercentage -Max | Select-Object -ExpandProperty Maximum\""
                res_util = subprocess.run(cmd_util, shell=True, capture_output=True, text=True, timeout=1.5)
                if res_util.returncode == 0 and res_util.stdout.strip():
                    metrics["gpu_pct"] = float(res_util.stdout.strip())
                else:
                    metrics["gpu_pct"] = 0.0
                    
                metrics["vram_pct"] = 0.0  # Shared memory used by Intel doesn't map directly to VRAM % in the same way
            except Exception:
                pass
            
    return metrics


from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from typing import Any

class TokenTrackerCallback(BaseCallbackHandler):
    """Callback handler to track prompt, completion, and total tokens from LLMResult across any provider (Groq, Ollama, OpenAI, etc.)."""
    def __init__(self):
        super().__init__()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            for generations in response.generations:
                for gen in generations:
                    # Try extraction from generation_info
                    if gen.generation_info and 'token_usage' in gen.generation_info:
                        usage = gen.generation_info['token_usage']
                        self.prompt_tokens += usage.get('prompt_tokens', 0)
                        self.completion_tokens += usage.get('completion_tokens', 0)
                        self.total_tokens += usage.get('total_tokens', 0)
                    elif gen.generation_info and 'usage' in gen.generation_info:
                        usage = gen.generation_info['usage']
                        self.prompt_tokens += usage.get('prompt_tokens', 0)
                        self.completion_tokens += usage.get('completion_tokens', 0)
                        self.total_tokens += usage.get('total_tokens', 0)
                    # Try extraction from message response_metadata
                    elif gen.message and hasattr(gen.message, 'response_metadata') and gen.message.response_metadata:
                        meta = gen.message.response_metadata
                        if 'token_usage' in meta:
                            self.prompt_tokens += meta['token_usage'].get('prompt_tokens', 0)
                            self.completion_tokens += meta['token_usage'].get('completion_tokens', 0)
                            self.total_tokens += meta['token_usage'].get('total_tokens', 0)
                        elif 'usage' in meta:
                            self.prompt_tokens += meta['usage'].get('prompt_tokens', 0)
                            self.completion_tokens += meta['usage'].get('completion_tokens', 0)
                            self.total_tokens += meta['usage'].get('total_tokens', 0)
        except Exception:
            pass


