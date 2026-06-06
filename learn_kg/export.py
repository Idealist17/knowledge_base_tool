from __future__ import annotations
import json
from pathlib import Path
from sqlalchemy import select
from .db import HistoricalDatabase
from . import schema as s


def export_dot(db: HistoricalDatabase, out: Path) -> None:
    lines = ["digraph KG {", "  rankdir=LR;"]
    with db.Session() as session:
        for p in session.scalars(select(s.Project)):
            lines.append(f'  p{p.id} [label="Project: {p.name}", color=blue];')
        for n in session.scalars(select(s.SemanticNode)):
            lines.append(f'  s{n.id} [label="S{n.id}: {n.name}", color=green];')
        for f in session.scalars(select(s.AuditFinding)):
            lines.append(f'  f{f.id} [label="F{f.id}: {f.title}", color=red];')
        for e in session.scalars(select(s.ProjectSemantic)):
            lines.append(f"  p{e.project_id} -> s{e.semantic_node_id};")
        for e in session.scalars(select(s.ProjectFinding)):
            lines.append(f"  p{e.project_id} -> f{e.audit_finding_id};")
        for e in session.scalars(select(s.SemanticMerge)):
            lines.append(f"  s{e.from_semantic_id} -> s{e.to_semantic_id} [style=dashed,label=merge];")
        for e in session.scalars(select(s.FindingMerge)):
            lines.append(f"  f{e.from_finding_id} -> f{e.to_finding_id} [style=dashed,label=merge];")
        for e in session.scalars(select(s.SemanticFindingLink)):
            lines.append(f"  s{e.semantic_node_id} -> f{e.audit_finding_id} [color=purple,label={e.strength!r}];")
    lines.append("}")
    out.write_text("\n".join(lines))


def export_html(db: HistoricalDatabase, out: Path) -> None:
    nodes = []; edges = []
    with db.Session() as session:
        raw_s = {x[0] for x in session.execute(select(s.SemanticMerge.from_semantic_id))}
        raw_f = {x[0] for x in session.execute(select(s.FindingMerge.from_finding_id))}
        for p in session.scalars(select(s.Project)):
            nodes.append({"id": f"p{p.id}", "label": p.name, "color": "#6ea8fe"})
        for n in session.scalars(select(s.SemanticNode)):
            nodes.append({"id": f"s{n.id}", "label": n.name, "color": "#b7efc5" if n.id in raw_s else "#52b788"})
        for f in session.scalars(select(s.AuditFinding)):
            nodes.append({"id": f"f{f.id}", "label": f.title, "color": "#f4a261" if f.id in raw_f else "#e63946"})
        for e in session.scalars(select(s.ProjectSemantic)): edges.append({"from": f"p{e.project_id}", "to": f"s{e.semantic_node_id}"})
        for e in session.scalars(select(s.ProjectFinding)): edges.append({"from": f"p{e.project_id}", "to": f"f{e.audit_finding_id}"})
        for e in session.scalars(select(s.SemanticMerge)): edges.append({"from": f"s{e.from_semantic_id}", "to": f"s{e.to_semantic_id}", "dashes": True, "label": "merge"})
        for e in session.scalars(select(s.FindingMerge)): edges.append({"from": f"f{e.from_finding_id}", "to": f"f{e.to_finding_id}", "dashes": True, "label": "merge"})
        for e in session.scalars(select(s.SemanticFindingLink)): edges.append({"from": f"s{e.semantic_node_id}", "to": f"f{e.audit_finding_id}", "color": "purple", "label": e.strength})
    out.write_text(f"""<!doctype html><html><head><meta charset='utf-8'><script src='https://unpkg.com/vis-network/standalone/umd/vis-network.min.js'></script><style>#kg{{height:95vh;border:1px solid #ddd}}</style></head><body><div id='kg'></div><script>const nodes=new vis.DataSet({json.dumps(nodes)});const edges=new vis.DataSet({json.dumps(edges)});new vis.Network(document.getElementById('kg'),{{nodes,edges}},{{physics:{{stabilization:true}},edges:{{arrows:'to'}}}});</script></body></html>""")


def export_counts(db: HistoricalDatabase) -> dict[str, int]:
    with db.Session() as session:
        return {
            "projects": len(list(session.scalars(select(s.Project)))),
            "semantics": len(list(session.scalars(select(s.SemanticNode)))),
            "findings": len(list(session.scalars(select(s.AuditFinding)))),
            "project_semantic_edges": len(list(session.scalars(select(s.ProjectSemantic)))),
            "project_finding_edges": len(list(session.scalars(select(s.ProjectFinding)))),
            "semantic_finding_edges": len(list(session.scalars(select(s.SemanticFindingLink)))),
        }
