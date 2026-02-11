import asyncio
from app.services.notion_client import get_notion_client

async def test():
    client = get_notion_client()
    
    # 議事録DBから最新のページを取得
    results = client.client.databases.query(
        database_id=client.meeting_database_id,
        page_size=1
    )
    if not results['results']:
        print('No meeting pages found')
        return
    
    meeting_page = results['results'][0]
    meeting_id = meeting_page['id']
    props = meeting_page['properties']
    
    title = props.get('タイトル', {}).get('title', [{}])
    title_text = title[0]['text']['content'] if title else 'unknown'
    print(f'Meeting page: {meeting_id} - {title_text}')
    
    # リレーションプロパティを全て表示
    print('\n--- All relation properties ---')
    for key in props:
        prop_type = props[key]['type']
        if prop_type == 'relation':
            rel_data = props[key]['relation']
            print(f'  "{key}": type=relation, values={rel_data}')
    
    # タスクDBから最新のタスクを取得
    from app.config import settings
    task_results = client.client.databases.query(
        database_id=settings.NOTION_TASK_DB_ID,
        page_size=1
    )
    if task_results['results']:
        task_page = task_results['results'][0]
        task_id = task_page['id']
        task_title = task_page['properties'].get('タスク名', {}).get('title', [{}])
        task_title_text = task_title[0]['text']['content'] if task_title else 'unknown'
        print(f'\nTask page: {task_id} - {task_title_text}')
        
        # 議事録ページのタスクリレーションを更新テスト
        print(f'\nTesting update_meeting_tasks_relation...')
        try:
            await client.update_meeting_tasks_relation(
                meeting_page_id=meeting_id,
                task_ids=[task_id]
            )
            print('SUCCESS: relation updated')
        except Exception as e:
            import traceback
            traceback.print_exc()
    else:
        print('No task pages found')

asyncio.run(test())
