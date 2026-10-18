"""Development preconditions: integrity and maturity; do not turn power analysis into a ban on exploration."""
from . import config, core, dataquality as dq, reference

def main():
 frame=config.load_frame();spec=frame['spec'];reg=config.load_features();problems=dq.manifest_problems()+reference.problems(spec)
 from . import checks
 original_report=checks.report
 try:
  checks.report=lambda name,ok,detail: problems.append(name+': '+detail) if not ok else None
  checks.i4_split_integrity(frame)
  checks.d3_registry_semantics(reg)
  checks.d7_label_maturity(frame)
 finally:checks.report=original_report
 df=core.load_dev(spec) # one-to-one complete join, binary labels
 delay=int(spec.get('label_delay_months',0))
 gap=int(spec['backtest']['gap_months'])
 if gap<delay:problems.append(f'gap {gap} < label delay {delay}')
 unknown=set(df.columns)-set(reg)-{'_month',spec['target_col']}
 if unknown:problems.append('undeclared columns: '+', '.join(sorted(unknown)))
 for name,train_end,start,end in core.windows(spec):
  if train_end>=start or end<start:problems.append('invalid window: '+name)
  if not (df['_month']<=train_end).any() or not df['_month'].between(start,end).any():problems.append('empty window: '+name)
 for p in problems:print(p)
 print('Development preconditions: '+('FAILURE' if problems else 'PASS; the runner then checks contracts and selected features'))
 return int(bool(problems))
if __name__=='__main__':raise SystemExit(main())
