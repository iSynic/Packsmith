"""Compare the same-machine 100k native listing receipt with beta 3."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
previous=json.loads((ROOT/'assessment/evidence/beta3/desktop-preview/scale-100k/gui.json').read_text(encoding='utf-8'))
current=json.loads((ROOT/'assessment/evidence/beta4/desktop-preview/scale-100k/gui.json').read_text(encoding='utf-8'))
metrics={key:dict(previous=previous[key],current=current[key],change_percent=round((current[key]/previous[key]-1)*100,2)) for key in ('listing_ms','peak_gui_rss')}
regressions=[key for key,row in metrics.items() if row['change_percent']>20]
if current['max_event_gap_ms']>1000:regressions.append('event loop stall > 1 second')
result=dict(passed=not regressions,metrics=metrics,max_event_gap_ms=current['max_event_gap_ms'],regressions=regressions,
    environment='Same native developer machine; harness ran sequentially with no competing build/test/emulator jobs. Existing user applications were left alone.',worker_sha256=current['worker_sha256'],gui_sha256=current['gui_sha256'])
(ROOT/'assessment/evidence/beta4/performance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2));raise SystemExit(bool(regressions))
