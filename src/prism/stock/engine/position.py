"""持仓台账 (本地 JSON)

持仓是**用户自己的账**, 不该塞进行情源里, 所以走本地文件:
    ~/.prism/positions.json      (PRISM_DIR 可改; 也可用 --file 指定别的路径)

文件结构 (人可读, 手改也行):
{
  "updated": "2026-10-24 18:00:00",
  "positions": [
    {"code": "600519", "name": "贵州茅台", "shares": 100, "cost": 1300.0,
     "note": "中线", "added": "2026-01-05"}
  ]
}

盈亏口径:
- 成本 = 每股成本价 (含手续费的摊薄由用户自己填), 市值 = 现价 × 股数
- 浮动盈亏 = (现价 - 成本) × 股数; 盈亏率 = 现价/成本 - 1
- 仓位 = 该股市值 / 组合总市值 (只算有现价的仓位)
- 止损/止盈由用户自己写死 (stop/target 字段), 命中就给提示
"""

__all__ = ['load', 'save', 'add', 'remove', 'positions', 'position_path',
           'normalize', 'validate_code']

import json
from datetime import datetime
from pathlib import Path

from prism.core.config_data import USER_DIR

FILE_NAME = 'positions.json'


def position_path(file=None) -> Path:
    if file:
        return Path(file).expanduser()
    return Path(USER_DIR) / FILE_NAME


def _empty() -> dict:
    return {'updated': None, 'positions': []}


def load(file=None) -> dict:
    """读台账; 文件不存在/坏了都返回空账 (不抛, 免得持仓文件坏了整条命令挂)"""
    p = position_path(file)
    try:
        data = json.loads(p.read_text())
    except Exception:
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    items = data.get('positions')
    return {'updated': data.get('updated'),
            'positions': items if isinstance(items, list) else []}


def save(data: dict, file=None) -> Path:
    p = position_path(file)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data or {})
    data['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return p


def validate_code(code) -> str:
    c = str(code or '').strip().upper()
    if not c:
        raise ValueError('代码不能为空')
    return c


def normalize(item: dict) -> dict:
    """一条持仓的字段归一 (数字转 float/int, 缺省补齐)"""
    out = {
        'code': validate_code(item.get('code')),
        'name': item.get('name') or '',
        'shares': int(float(item.get('shares') or 0)),
        'cost': float(item.get('cost') or 0),
        'note': item.get('note') or '',
        'added': item.get('added') or '',
    }
    if item.get('stop') not in (None, ''):
        out['stop'] = float(item['stop'])
    if item.get('target') not in (None, ''):
        out['target'] = float(item['target'])
    return out


def positions(file=None) -> list:
    return [normalize(it) for it in load(file).get('positions') or []
            if isinstance(it, dict) and it.get('code')]


def add(code, shares, cost, name='', note='', stop=None, target=None,
        file=None) -> dict:
    """加仓/建仓: 同代码已存在则合并股数与加权成本"""
    data = load(file)
    items = [it for it in data.get('positions') or [] if isinstance(it, dict)]
    code = validate_code(code)
    shares = int(float(shares or 0))
    cost = float(cost or 0)
    if shares <= 0:
        raise ValueError('股数必须大于 0')
    if cost <= 0:
        raise ValueError('成本价必须大于 0')
    hit = None
    for it in items:
        if str(it.get('code', '')).upper() == code:
            hit = it
            break
    if hit:
        old_shares = int(float(hit.get('shares') or 0))
        old_cost = float(hit.get('cost') or 0)
        total = old_shares + shares
        new_cost = ((old_cost * old_shares) + (cost * shares)) / total if total else cost
        hit['shares'] = total
        hit['cost'] = round(new_cost, 4)
        if name:
            hit['name'] = name
        if note:
            hit['note'] = note
        if stop:
            hit['stop'] = float(stop)
        if target:
            hit['target'] = float(target)
    else:
        new = {'code': code, 'name': name or '', 'shares': shares,
               'cost': round(cost, 4), 'note': note,
               'added': datetime.now().strftime('%Y-%m-%d')}
        if stop:
            new['stop'] = float(stop)
        if target:
            new['target'] = float(target)
        items.append(new)
    data['positions'] = items
    path = save(data, file)
    return {'ok': True, 'file': str(path), 'count': len(items)}


def remove(code, shares=None, file=None) -> dict:
    """减仓/清仓: 给了股数就减这么多, 不给就整条删掉"""
    data = load(file)
    items = [it for it in data.get('positions') or [] if isinstance(it, dict)]
    code = validate_code(code)
    keep, hit = [], None
    for it in items:
        if str(it.get('code', '')).upper() == code:
            hit = it
            continue
        keep.append(it)
    if hit is None:
        return {'ok': False, 'error': f'没有 {code} 的持仓'}
    if shares:
        left = int(float(hit.get('shares') or 0)) - int(float(shares))
        if left > 0:
            hit['shares'] = left
            keep.append(hit)
    data['positions'] = keep
    path = save(data, file)
    return {'ok': True, 'file': str(path), 'count': len(keep)}
