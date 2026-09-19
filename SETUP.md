# Setup — VS Code, from zero

Commands are written for **Windows PowerShell** (the VS Code default on Windows).
macOS / Linux variants are noted where they differ.

---

## 0. Before anything else — start the big install

`sentence-transformers` pulls in PyTorch, roughly 2 GB. Kick it off first and read
the rest while it runs.

---

## 1. Folder + VS Code

```powershell
mkdir credit-risk
cd credit-risk
code .
```

Drop the provided files into this folder:

```
credit-risk/
├── app.py
├── scorer.py
├── rag.py
├── model.py          (optional, hour 5)
├── policies.md
├── requirements.txt
├── README.md
└── CONTEXT.md
```

## 2. Python extension

In VS Code: Extensions panel (`Ctrl+Shift+X`) → install **Python** (Microsoft).
That is the only extension you need. Pylance comes with it.

## 3. Virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate`

If PowerShell blocks the activate script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then point VS Code at it: `Ctrl+Shift+P` → **Python: Select Interpreter** →
choose the one ending in `.venv`. The status bar bottom-left should now read
`.venv`. If it does not, your terminal and your editor are using different
Pythons and you will get phantom import errors all day.

## 4. Install

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Ten to fifteen minutes on a decent connection. If torch is too slow, see
"Escape hatch" at the bottom.

## 5. API key — Groq (free tier)

Go to **console.groq.com**, sign in (Google/GitHub works), and create an API key
under API Keys. No credit card required. The free tier's rate limit is generous
enough for a demo/portfolio project — you will not hit it building this.

Create a file named `.env` in the project root:

```
GROQ_API_KEY=gsk_...
```

Verify it actually saved (not still a placeholder) before moving on:

```powershell
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(repr(os.environ.get('GROQ_API_KEY')))"
```

**Fully local / no signup at all — Ollama.** If you'd rather not create any
account, install Ollama (ollama.com), run `ollama pull llama3.2`, and swap
`rag.py`'s `explain()` to:

```python
from langchain_ollama import ChatOllama
llm = ChatOllama(model="llama3.2", temperature=0)
```

No `.env` needed for this path, but responses are slower and quality is lower
than Groq's 70B model. Needs `pip install langchain-ollama` and the Ollama app
running locally.

Add these two lines at the top of `rag.py`, above the other imports (needed
regardless of which provider you use):

```python
from dotenv import load_dotenv
load_dotenv()
```

Create `.gitignore` in the same folder:

```
.venv/
.env
faiss_index/
pd_model.joblib
data/
__pycache__/
```

Commit the `.gitignore` before you commit anything else. A leaked key in git
history is a bad afternoon.

## 6. First run

```powershell
streamlit run app.py
```

Opens at `http://localhost:8501`. The first assessment is slow — it downloads the
MiniLM embedding model (~90 MB) and builds `faiss_index/`. Subsequent runs are fast.

Sanity check with the DTI decline case: income 50000, existing debt 20000,
amount 900000, score 760, tenure 48. You should get **DECLINE**, band D, and a memo
whose principal reason cites POL-001.

## 7. Debugging in VS Code

`F5` won't work on Streamlit out of the box. Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Streamlit",
      "type": "debugpy",
      "request": "launch",
      "module": "streamlit",
      "args": ["run", "app.py"],
      "justMyCode": false
    }
  ]
}
```

Now breakpoints work — put one in `scorer.assess` and step through a decline.

## 8. Optional — the PD model (hour 5 only)

Download `german_credit_data.csv` from the Kaggle page into `data/`, then:

```powershell
python model.py
```

Prints holdout AUC and writes `pd_model.joblib`. Expect AUC 0.74–0.78. If you see
0.95, you leaked the target.

---

## Escape hatch

If the torch install stalls or you are short on disk, drop
`sentence-transformers` and `langchain-huggingface`, and swap the embeddings in
`rag.py`:

```python
from langchain_voyageai import VoyageAIEmbeddings
def _embeddings():
    return VoyageAIEmbeddings(model="voyage-3-lite")
```

Needs a Voyage API key, but installs in seconds. Delete `faiss_index/` after any
embedding change — a FAISS index built with one model cannot be queried with another.

## Common failures

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError` despite installing | VS Code interpreter ≠ terminal venv. Redo step 3. |
| `KeyError: 'GROQ_API_KEY'` | `.env` missing, or `load_dotenv()` not added to `rag.py`. |
| `401` from Groq | Key wasn't actually saved into `.env` — check with the `repr()` command above; a placeholder string is the usual cause. |
| Retrieved policies look random | Stale `faiss_index/`. Delete the folder and rerun. |
| Memo contradicts the scorecard | System prompt in `rag.py` was edited. The decision is passed in, never inferred. |
| Streamlit reruns the whole script on every widget | That is normal. `@st.cache_resource` protects the index. |
