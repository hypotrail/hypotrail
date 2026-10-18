"""Local VSIX packaging without build dependencies or publication."""
from pathlib import Path
import shutil,json,zipfile
root=Path(__file__).resolve().parents[1];tutorial=root.parent/'runtime'
for folder,names in {'assets':['companion.html','companion.js','bridge.js','markdown.js','design.css'],'engine':['bridge.py','protocol.py','contracts.py']}.items():
 (root/folder).mkdir(exist_ok=True)
 for stale in (root/folder).glob('*'):
  if stale.is_file() and stale.name not in names:stale.unlink()
 for name in names:shutil.copy2(tutorial/name,root/folder/name)
# Public contracts and data (CC BY 4.0) keep the packaged engine self-contained.
for sub in ['projects','journeys']:
 shutil.rmtree(root/'engine'/sub,ignore_errors=True)
 shutil.copytree(tutorial/sub,root/'engine'/sub,ignore=shutil.ignore_patterns('*.pyc','__pycache__','Index','*.data-original'))
(root/'engine/data').mkdir(exist_ok=True);shutil.copy2(tutorial/'data/bank.csv',root/'engine/data/bank.csv')
package=json.loads((root/'package.json').read_text());dest=root/('hypotrail-companion-'+package['version']+'.vsix')
manifest=f'''<?xml version="1.0" encoding="utf-8"?><PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="{package['name']}" Version="{package['version']}" Publisher="{package['publisher']}"/><DisplayName>Hypotrail Companion</DisplayName><Description xml:space="preserve">Atelier Bank Marketing local</Description><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.100.0"/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>'''
ct='''<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="html" ContentType="text/html"/><Default Extension="css" ContentType="text/css"/><Default Extension="py" ContentType="text/plain"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="csv" ContentType="text/csv"/><Default Extension="data" ContentType="text/plain"/><Default Extension="names" ContentType="text/plain"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>'''
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('extension.vsixmanifest',manifest);z.writestr('[Content_Types].xml',ct)
 # Never package the simulated provider or test directory.
 for name in ['package.json','extension.js','engine.js','assistant.js','prompt.js','lm.js','router.js','README.md']:z.write(root/name,'extension/'+name)
 for folder in ['assets','engine']:
  for p in sorted((root/folder).rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts:z.write(p,'extension/'+p.relative_to(root).as_posix())
print(dest)
