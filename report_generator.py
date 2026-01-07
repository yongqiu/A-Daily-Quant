import markdown
import os
from datetime import datetime

def generate_html_report(md_content_holdings: str, md_content_candidates: str, output_path: str):
    """
    Convert separate Markdown content sections to a styled HTML report with tabs
    """
    
    # Custom CSS for a dashboard look
    css = """
    <style>
        :root {
            --primary-color: #2563eb;
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
            --success-color: #16a34a;
            --danger-color: #dc2626;
            --warning-color: #d97706;
            --tab-active-bg: #2563eb;
            --tab-active-text: #ffffff;
            --tab-inactive-bg: #e2e8f0;
            --tab-inactive-text: #475569;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-main);
            background-color: var(--bg-color);
            margin: 0;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        /* Headers */
        h1 {
            font-size: 2.2rem;
            color: #0f172a;
            border-bottom: 3px solid var(--primary-color);
            padding-bottom: 15px;
            margin-bottom: 30px;
            text-align: center;
        }
        
        h2 { 
            font-size: 1.5rem; 
            background: var(--card-bg);
            padding: 15px 20px;
            border-radius: 8px 8px 0 0;
            border-top: 4px solid var(--primary-color);
            margin-top: 40px;
            margin-bottom: 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
        }
        
        h3 {
            font-size: 1.1rem;
            color: #334155;
            margin-top: 20px;
            margin-bottom: 10px;
            font-weight: 600;
            border-left: 3px solid #cbd5e1;
            padding-left: 10px;
        }
        
        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            margin: 15px 0;
            font-size: 0.95rem;
        }
        
        th, td {
            padding: 10px 15px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        
        th {
            background-color: #f1f5f9;
            font-weight: 600;
            color: #475569;
        }
        
        tr:last-child td { border-bottom: none; }
        
        /* Lists */
        ul { 
            padding-left: 20px; 
            background: var(--card-bg);
            padding: 15px 15px 15px 35px;
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            margin: 10px 0;
        }
        
        li { margin-bottom: 6px; }
        
        /* Paragraphs & Text */
        p { margin-bottom: 1em; }
        
        strong { font-weight: 700; color: #0f172a; }
        
        /* Tab Styling */
        .tabs {
            display: flex;
            margin-bottom: 20px;
            border-bottom: 2px solid var(--border-color);
        }
        
        .tab-button {
            padding: 12px 24px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            border: none;
            background-color: var(--tab-inactive-bg);
            color: var(--tab-inactive-text);
            border-radius: 8px 8px 0 0;
            margin-right: 5px;
            transition: all 0.3s ease;
        }
        
        .tab-button:hover {
            background-color: #cbd5e1;
        }
        
        .tab-button.active {
            background-color: var(--tab-active-bg);
            color: var(--tab-active-text);
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.5s;
        }
        
        .tab-content.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        /* Special styling for the Beta Shield section (usually first h2) */
        h2:first-of-type {
            border-top-color: var(--warning-color);
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
            body { padding: 10px; }
            h1 { font-size: 1.8rem; }
            h2 { font-size: 1.3rem; }
             table { display: block; overflow-x: auto; }
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