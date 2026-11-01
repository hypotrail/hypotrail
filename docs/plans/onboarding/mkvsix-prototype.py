"""Pure-Python VSIX builder (experiment). Usage: mkvsix.py SRC OUT"""
import json, sys, zipfile, mimetypes
from pathlib import Path
from xml.sax.saxutils import escape
src, out = Path(sys.argv[1]), Path(sys.argv[2])
pkg = json.loads((src/'package.json').read_text(encoding='utf-8'))
files = {'extension/package.json': src/'package.json', 'extension/extension.js': src/'extension.js',
         'extension/readme.md': src/'README.md'}
for d in ('lib', 'media'):
    for p in sorted((src/d).rglob('*')):
        if p.is_file(): files['extension/'+p.relative_to(src).as_posix()] = p
manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
<Metadata>
<Identity Language="en-US" Id="{escape(pkg['name'])}" Version="{escape(pkg['version'])}" Publisher="{escape(pkg['publisher'])}" />
<DisplayName>{escape(pkg.get('displayName', pkg['name']))}</DisplayName>
<Description xml:space="preserve">{escape(pkg.get('description',''))}</Description>
<Tags></Tags><Categories>{escape(','.join(pkg.get('categories',[])))}</Categories><GalleryFlags>Public</GalleryFlags>
<Properties>
<Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(pkg['engines']['vscode'])}" />
<Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
<Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
<Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
<Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />
<Property Id="Microsoft.VisualStudio.Code.EnabledApiProposals" Value="" />
<Property Id="Microsoft.VisualStudio.Code.ExecutesCode" Value="true" />
<Property Id="Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown" Value="true" />
<Property Id="Microsoft.VisualStudio.Services.Content.Pricing" Value="Free"/>
</Properties>
</Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
<Dependencies/>
<Assets>
<Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
<Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/readme.md" Addressable="true" />
</Assets>
</PackageManifest>
'''
exts = sorted({Path(n).suffix.lower() for n in files} | {'.vsixmanifest'})
types = {'.vsixmanifest': 'text/xml', '.json': 'application/json', '.js': 'application/javascript',
         '.md': 'text/markdown', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.html': 'text/html'}
ct = '<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' + \
     ''.join(f'<Default Extension="{e}" ContentType="{types.get(e) or mimetypes.guess_type("x"+e)[0] or "application/octet-stream"}"/>' for e in exts) + '</Types>'
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    def put(name, data):
        zi = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED; z.writestr(zi, data)
    put('extension.vsixmanifest', manifest); put('[Content_Types].xml', ct)
    for n, p in files.items(): put(n, p.read_bytes())
