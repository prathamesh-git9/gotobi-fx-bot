from pathlib import Path

lines = Path("codex_run.log").read_text(encoding="utf-8", errors="replace").splitlines()
start = next(i for i, line in enumerate(lines) if line.startswith("diff --git ") and line.endswith("/research.py b/codex_audit/smc_research/research.py"))
content = []
inside = False
for line in lines[start + 1:]:
    if line.startswith("diff --git "):
        break
    if line.startswith("@@ "):
        inside = True
        continue
    if not inside:
        continue
    if line.startswith("-") or line.startswith(" "):
        content.append(line[1:])
Path("research_4.py").write_text("\n".join(content) + "\n", encoding="utf-8")
print("Recovered", len(content), "lines")
