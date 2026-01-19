import markdown
import os
from datetime import datetime

def generate_html_report(md_content_holdings: str, md_content_candidates: str, output_path: str):
    """
    Convert separate Markdown content sections to a styled HTML report with tabs
    """
    
    # Custom CSS for a dashboard look (Dark Mode)
    css = """
    <style>
        :root {
            --bg-color: #0a0c10;
            --card-bg: #161a22;
            --border-color: #30363d;
            
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            
            --accent-color: #58a6ff;
            --accent-dim: rgba(56, 139, 253, 0.1);
            
            --success-color: #3fb950;
            --danger-color: #f85149;
            --warning-color: #d29922;
            
            --tab-active-bg: rgba(56, 139, 253, 0.15);
            --tab-active-text: #58a6ff;
            --tab-inactive-bg: transparent;
            --tab-inactive-text: #8b949e;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background-color: var(--bg-color);
            margin: 0;
            padding: 40px 20px;
            -webkit-font-smoothing: antialiased;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        /* Headers */
        h1 {
            font-size: 2rem;
            color: var(--text-primary);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
            margin-bottom: 40px;
            text-align: center;
            letter-spacing: -0.5px;
        }
        
        h2 {
            font-size: 1.5rem;
            color: var(--accent-color);
            margin-top: 50px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(88, 166, 255, 0.2);
            display: flex;
            align-items: center;
        }
        
        h3 {
            font-size: 1.15rem;
            color: var(--text-primary);
            margin-top: 30px;
            margin-bottom: 15px;
            font-weight: 600;
        }
        
        /* Tables */
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            background: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            margin: 20px 0;
            font-size: 0.95rem;
        }
        
        th, td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        
        th {
            background-color: #21262d;
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 0.85rem;
            text-transform: uppercase;
        }
        
        tr:last-child td { border-bottom: none; }
        tr:hover td { background-color: rgba(110, 118, 129, 0.05); }
        
        /* Lists */
        ul {
            padding-left: 20px;
            color: var(--text-secondary);
            margin: 15px 0;
        }
        
        li { margin-bottom: 8px; }
        
        /* Paragraphs & Text */
        p { margin-bottom: 1.2em; color: #c9d1d9; }
        
        strong { font-weight: 600; color: var(--text-primary); }
        
        /* Blockquotes */
        blockquote {
            border-left: 4px solid var(--accent-color);
            margin: 20px 0;
            padding: 10px 20px;
            color: var(--text-secondary);
            background: rgba(88, 166, 255, 0.05);
            border-radius: 0 4px 4px 0;
        }
        
        /* Code */
        code {
            background: rgba(110, 118, 129, 0.2);
            padding: 0.2em 0.4em;
            border-radius: 6px;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
            font-size: 0.85em;
        }
        
        /* Tab Styling */
        .tabs {
            display: flex;
            margin-bottom: 30px;
            border-bottom: 1px solid var(--border-color);
            gap: 10px;
        }
        
        .tab-button {
            padding: 12px 20px;
            font-size: 0.95rem;
            font-weight: 500;
            cursor: pointer;
            border: 1px solid transparent;
            background-color: transparent;
            color: var(--tab-inactive-text);
            border-radius: 6px 6px 0 0;
            transition: all 0.2s ease;
            margin-bottom: -1px;
        }
        
        .tab-button:hover {
            color: var(--text-primary);
        }
        
        .tab-button.active {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-bottom-color: var(--card-bg);
            color: var(--text-primary);
            font-weight: 600;
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s ease-out;
            background: var(--card-bg); /* Add card background to content */
            padding: 30px;
            border-radius: 0 0 8px 8px; /* Round bottom corners */
            border: 1px solid var(--border-color);
            border-top: none; /* Align with tabs */
            margin-top: -1px; /* Overlap border */
        }
        
        .tab-content.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Footer */
        .footer {
            text-align: center;
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 60px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
        }
        
        /* Responsive */
        @media (max-width: 600px) {
            body { padding: 20px 10px; }
            h1 { font-size: 1.5rem; }
            h2 { font-size: 1.2rem; }
            table { display: block; overflow-x: auto; white-space: nowrap; }
            .tab-button { padding: 10px 15px; font-size: 0.9rem; }
        }
    </style>
    <script>
        function openTab(evt, tabName) {
            var i, tabcontent, tablinks;
            
            // Hide all tab content
            tabcontent = document.getElementsByClassName("tab-content");
            for (i = 0; i < tabcontent.length; i++) {
                tabcontent[i].style.display = "none";
                tabcontent[i].classList.remove("active");
            }
            
            // Remove active class from all tab buttons
            tablinks = document.getElementsByClassName("tab-button");
            for (i = 0; i < tablinks.length; i++) {
                tablinks[i].classList.remove("active");
            }
            
            // Show the specific tab content
            document.getElementById(tabName).style.display = "block";
            document.getElementById(tabName).classList.add("active");
            
            // Add active class to the button that opened the tab
            evt.currentTarget.classList.add("active");
        }
    </script>
    """
    
    # Convert MD to HTML with extensions
    html_holdings = markdown.markdown(md_content_holdings, extensions=['tables', 'fenced_code', 'nl2br'])
    html_candidates = markdown.markdown(md_content_candidates, extensions=['tables', 'fenced_code', 'nl2br'])
    
    # Combine into full HTML with Tabs
    full_html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>A股交易策略日报</title>
        {css}
    </head>
    <body>
        <div class="container">
            <h1>A股交易策略日报</h1>
            
            <div class="tabs">
                <button class="tab-button active" onclick="openTab(event, 'holdings')">📊 持仓分析</button>
                <button class="tab-button" onclick="openTab(event, 'candidates')">🎯 选股参考</button>
            </div>
            
            <div id="holdings" class="tab-content active">
                {html_holdings}
            </div>
            
            <div id="candidates" class="tab-content">
                {html_candidates}
            </div>
            
            <div class="footer">
                生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
    </body>
    </html>
    """
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
        
    return output_path