import html
from pyvis.network import Network
from src.algorithms import COMMUNITY_COLORS

COLORS = {'IES':'#2563eb','Curso':'#8b5cf6','OfertaCurso':'#ea580c','Municipio':'#059669','UF':'#0d9488','Trecho':'#db2777','Documento':'#64748b'}

def render_graph(context):
    has_communities = any(n.get('community') is not None for n in context['nodes'])
    net = Network(height='570px',width='100%',directed=True,bgcolor='#f8fafc',font_color='#172033',cdn_resources='in_line')
    for node in context['nodes']:
        name = node['name']
        community = node.get('community')
        if has_communities and community is not None:
            color = COMMUNITY_COLORS[int(community) % len(COMMUNITY_COLORS)]
        else:
            color = COLORS.get(node['kind'],'#94a3b8')
        title = f"{node['kind']}: {name}\nID: {node['key']}\nFonte: {node['source']}"
        if community is not None:
            title += f"\nComunidade (Louvain): {community}"
        net.add_node(node['id'],label=name[:44]+('…' if len(name)>44 else ''),
            title=html.escape(title),
            color=color,size=12+80*node['pagerank'])
    for edge in context['edges']:
        net.add_edge(edge['source'],edge['target'],title=html.escape(edge['type']),label=edge['type'],color='#cbd5e1')
    net.set_options('''{"physics":{"solver":"forceAtlas2Based","stabilization":{"iterations":160}},"interaction":{"hover":true,"navigationButtons":true},"edges":{"font":{"size":8},"smooth":false},"nodes":{"font":{"size":11}}}''')
    return net.generate_html(notebook=False)
