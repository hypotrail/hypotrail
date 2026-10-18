"""Standalone export styling; no calculation or decision change."""
from pathlib import Path
import re

def polish(document, *, quality=False):
    css=(Path(__file__).parent/'assets/design.css').read_text()
    base='../../../reports/' if quality else ''
    nav='<header class="export-nav"><span class="brand">Hypotrail</span><nav><a href="'+base+'pilot.html">The journey</a><a href="'+base+'dataset-discovery.html">Data</a><a href="'+base+'classical-study.html">Comparison</a></nav><span class="export-mode">Offline snapshot</span><button id="theme" onclick="document.body.classList.toggle(\'dark\')">Light / dark</button></header>'
    # Classical exports have one navigation bar; historical pages retain their links.
    if 'class="top"' not in document:
        document=re.sub(r'<header\b[^>]*>.*?</header>','',document,count=1,flags=re.S)
        document=document.replace('<button onclick="document.body.classList.toggle(\'dark\')">Light / dark</button>','')
    document=document.replace('</head>', '<style>'+css+'</style></head>',1) if '</head>' in document else document.replace('</style>','</style><style>'+css+'</style>',1)
    if '<body>' in document:document=document.replace('<body>','<body class="report">'+nav,1)
    elif '<body ' in document:document=document.replace('<body ', '<body class="report" ',1).replace('<main>',nav+'<main>',1)
    else:document=document.replace('<main>','<body class="report">'+nav+'<main>',1)
    script="""<script>(()=>{try{document.body.classList.toggle('dark',localStorage.getItem('osml-theme')==='dark')}catch(_){};const b=document.getElementById('theme');if(b)b.addEventListener('click',()=>{try{localStorage.setItem('osml-theme',document.body.classList.contains('dark')?'dark':'light')}catch(_){}})})();</script>"""
    return document.replace('</body>',script+'</body>',1) if '</body>' in document else document.replace('</html>',script+'</body></html>')
