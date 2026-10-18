"""Export teaching notebooks to HTML without refitting models."""
import importlib.util,subprocess,sys
from . import config

def main():
 if importlib.util.find_spec('marimo') is None:
  print('Notebooks not exported: install requirements-pilot.txt. Python sources remain available.');return 2
 for name in (['discovery','study'] if (config.ROOT/'project.yaml').exists() else ['data','residuals']):
  result=subprocess.run([sys.executable,'-m','marimo','export','html',str(__import__('pathlib').Path(__file__).resolve().parents[1]/'notebooks'/f'{name}.py'),'--force','-o',str(config.ROOT/'reports'/f'{name}-notebook.html')],cwd=config.ROOT,timeout=240)
  if result.returncode:return result.returncode
 print('HTML notebooks ready in reports/');return 0
if __name__=='__main__':raise SystemExit(main())
