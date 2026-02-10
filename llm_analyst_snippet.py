
def create_deep_candidate_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a DEEP MONITOR prompt for A-share stocks using 'deep_monitor' template.
    Focuses on Real-time Money Flow, Sector, and Market Context.
    """
    print(f"Deep Monitor: {stock_info['symbol']} - {stock_info['name']}")
    
    # 1. Prepare computed details for template convenience if needed
    # The template 'deep_monitor' uses:
    # - stock_info.name
    # - realtime_data.change_pct
    # - realtime_data.money_flow.net_amount_main
    # - tech_data.sector
    # - tech_data.sector_change
    # - realtime_data.market_index_status (or derived from context)
    # - tech_data.composite_score
    
    # Ensure money_flow exists
    if 'money_flow' not in realtime_data or not realtime_data['money_flow']:
        realtime_data['money_flow'] = {'net_amount_main': 'N/A'}
        
    # Ensure sector details exist
    if 'sector' not in tech_data:
        tech_data['sector'] = '未知'
    if 'sector_change' not in tech_data:
        tech_data['sector_change'] = 0
        
    db_prompt = get_prompt_from_db('deep_monitor', {
        'stock_info': stock_info,
        'tech_data': tech_data,
        'realtime_data': realtime_data
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: deep_monitor prompt not found."

