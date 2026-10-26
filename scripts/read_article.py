"""Use installed WeChat MCP servers from sessions where native tools aren't loaded."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(os.environ['WECHAT_READER_ROOT']).expanduser() if os.environ.get('WECHAT_READER_ROOT') else None

def unpack(result):
    structured = getattr(result, 'structured_content', None)
    if structured is not None:
        return structured
    texts = [part.text for part in result.content if getattr(part, 'type', None) == 'text']
    text = '\n'.join(texts)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'content': text, 'is_error': getattr(result, 'is_error', False)}

async def fetch(backend, url=None):
    if backend == 'readgzh':
        transport = 'https://api.readgzh.site/mcp-server'
    else:
        if ROOT is None:
            raise ValueError('Set WECHAT_READER_ROOT to the installed local reader directory')
        env = dict(os.environ)
        env['PATH'] = str(ROOT / 'bin') + os.pathsep + env.get('PATH', '')
        env['PYTHONIOENCODING'] = 'utf-8'
        local_python = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
        executable = os.environ.get('WECHAT_READER_PYTHON') or (str(local_python) if local_python.exists() else sys.executable)
        transport = StdioTransport(command=executable,
            args=[str(ROOT / 'src/server.py')], env=env)
    async with Client(transport, timeout=90) as client:
        inventory = await client.list_tools()
        if url is None:
            return {'backend': backend, 'tools': [t.model_dump(mode='json') for t in inventory]}
        name = 'readgzh.read' if backend == 'readgzh' else 'read_weixin_article'
        return {'backend': backend, 'result': unpack(await client.call_tool(name, {'url': url}))}

def valid(response):
    result = response.get('result', {})
    if not isinstance(result, dict) or result.get('success') is False or result.get('is_error'):
        return False
    content = result.get('content') or result.get('data', {}).get('content')
    return isinstance(content, str) and len(content.strip()) > 100 and not any(
        s in content[:500] for s in ('当前环境异常', '完成验证后', '该内容已被发布者删除'))

async def main(args):
    if args.url:
        parsed = urlsplit(args.url)
        if not (parsed.scheme == 'https' and parsed.hostname == 'mp.weixin.qq.com'
                and (parsed.path == '/s' or parsed.path.startswith('/s/'))):
            raise ValueError('Expected a public mp.weixin.qq.com article URL')
    backends = ['readgzh', 'local'] if args.backend == 'auto' else [args.backend]
    attempts = []
    for backend in backends:
        try:
            response = await asyncio.wait_for(fetch(backend, args.url), timeout=110)
        except Exception as exc:
            response = {'backend': backend, 'error': f'{type(exc).__name__}: {exc}'}
        attempts.append(response)
        if args.url and valid(response):
            break
    output = {'url': args.url, 'attempts': attempts}
    if args.output:
        Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    for response in attempts:
        if not args.url:
            print(json.dumps({'backend': response['backend'], 'tools': [t['name'] for t in response.get('tools', [])], 'error': response.get('error')}, ensure_ascii=False))
        else:
            result = response.get('result', {})
            print(json.dumps({'backend': response['backend'], 'has_content': valid(response),
                'title': result.get('title') if isinstance(result, dict) else None,
                'error': response.get('error') or (result.get('error') if isinstance(result, dict) else None),
                'output': args.output}, ensure_ascii=False))
    if args.url and not any(valid(r) for r in attempts):
        raise SystemExit(1)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('url', nargs='?')
    p.add_argument('--backend', choices=['auto', 'readgzh', 'local'], default='auto')
    p.add_argument('--output')
    asyncio.run(main(p.parse_args()))
