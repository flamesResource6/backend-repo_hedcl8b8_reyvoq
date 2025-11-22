import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from database import create_document, get_documents
from schemas import Blueprint, GraphNode, GraphEdge

app = FastAPI(title="Blueprint Imperium API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ParseRequest(BaseModel):
    message: str

class CreateBlueprintRequest(BaseModel):
    title: str
    message: str

@app.get("/")
def read_root():
    return {"message": "Blueprint Imperium Backend running"}

@app.get("/test")
def test_database():
    from database import db
    ok = db is not None
    return {
        "backend": "✅ Running",
        "database": "✅ Connected" if ok else "❌ Not Connected",
    }

@app.post("/api/parse", response_model=Blueprint)
def parse_message(payload: ParseRequest):
    # Very simple parser for a subset of Mermaid graph definitions found in the prompt
    text = payload.message
    if not text.lower().strip().startswith("mordo"):
        raise HTTPException(status_code=400, detail="Wiadomość musi zaczynać się od 'mordo'")

    # Extract mermaid block if present
    lines = text.splitlines()
    in_graph = False
    nodes = {}
    edges: List[GraphEdge] = []
    groups = {}

    for ln in lines:
        s = ln.strip()
        if s.startswith("graph "):
            in_graph = True
            continue
        if not in_graph:
            continue
        if s.startswith("subgraph "):
            # subgraph NAME [LABEL]
            parts = s.split(" ", 2)
            current_group = s
            groups[current_group] = []
            continue
        if s.startswith("end"):
            current_group = None
            continue
        # Node definitions like: A[TONY HK LTD]
        if "[" in s and "]" in s and "-->" not in s and "-.->" not in s:
            try:
                nid = s.split("[")[0]
                label = s.split("[")[1].split("]")[0]
                nid = nid.strip()
                nodes[nid] = GraphNode(id=nid, label=label)
            except Exception:
                pass
        # Edges like: A -- "label" --> B  or  C -.-> FB
        if "-->" in s or "-.->" in s:
            style = "dashed" if "-.->" in s else "solid"
            arrow = "-.->" if style == "dashed" else "-->"
            left, right = s.split(arrow)
            src = left.split("--")[0].strip()
            tgt = right.strip().split(" ")[0]
            # label between quotes
            label = None
            if "\"" in s:
                try:
                    label = s.split("\"")[1]
                except Exception:
                    label = None
            edges.append(GraphEdge(source=src, target=tgt, label=label, style=style))
            # Ensure nodes exist
            if src not in nodes:
                nodes[src] = GraphNode(id=src, label=src)
            if tgt not in nodes:
                nodes[tgt] = GraphNode(id=tgt, label=tgt)

    bp = Blueprint(title="Blueprint z rozmowy", raw_text=text, nodes=list(nodes.values()), edges=edges)
    return bp

@app.post("/api/blueprints", response_model=str)
def create_blueprint(payload: CreateBlueprintRequest):
    bp = parse_message(ParseRequest(message=payload.message))
    bp.title = payload.title
    try:
        inserted_id = create_document("blueprint", bp)
        return inserted_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/blueprints", response_model=List[Blueprint])
def list_blueprints():
    try:
        docs = get_documents("blueprint")
        # Map raw documents to Blueprint while ignoring unknown fields like _id/timestamps
        result: List[Blueprint] = []
        for d in docs:
            nodes = [GraphNode(**n) for n in d.get("nodes", [])]
            edges = [GraphEdge(**e) for e in d.get("edges", [])]
            result.append(Blueprint(
                title=d.get("title", "Blueprint"),
                raw_text=d.get("raw_text", ""),
                nodes=nodes,
                edges=edges,
                metadata=d.get("metadata", {}),
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
