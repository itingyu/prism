"""prism schema: 让调用方能自描述 —— 命令有哪些参数, JSON 出来长什么样

给 agent / 脚本用: 以前想知道 `prism lhb -f json` 的结构, 只能先跑一次,
看返回了什么; 现在直接问。

    prism schema lhb              # 单个命令: 参数 + 信封形状 + 口径清单
    prism schema lhb --kind xx    # 指定口径 (行字段由上游接口决定, 这里给接口名)
    prism schema --all            # 全部命令的目录 (命令名/动作/参数/口径数)
"""
import inspect

from prism.stock.command._envelope import describe


def _params_of(fn):
    """从命令函数的签名里抽出参数说明 (名字/类型/是否必填/默认值)"""
    out = []
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return out
    for p in sig.parameters.values():
        if p.name in ('fmt', 'output'):
            continue
        d = p.default
        # typer 的默认值是 OptionInfo/ArgumentInfo 对象, 取里面的真值
        if hasattr(d, 'default'):
            d = d.default
        info = {
            'name': p.name,
            'type': 'str' if p.annotation is str else
                    ('int' if p.annotation is int else
                     ('bool' if p.annotation is bool else 'str')),
            'required': p.default is inspect.Parameter.empty,
        }
        if p.default is not inspect.Parameter.empty and not isinstance(
                d, (bool, list, dict)) and d is not None:
            info['default'] = d
        out.append(info)
    return out


def _family_of(name):
    """命令名 → 它挂着的功能族 (有 --kind 的命令才有)"""
    try:
        from prism.stock.bridge.ak_families import FAM
    except Exception:
        return None
    return name if name in FAM else None


def command_schema(name, commands, kind=None):
    """单个命令的 schema"""
    fn = commands.get(name)
    if fn is None:
        raise ValueError(f'没有这个命令: {name} (用 prism schema --all 看全部)')
    doc = (fn.__doc__ or '').strip().splitlines()
    fam = _family_of(name)
    kinds = []
    if fam:
        from prism.stock.bridge.ak_families import FAM
        kinds = sorted(FAM[fam].keys())
    out = {
        'command': name,
        'summary': doc[0] if doc else '',
        'params': _params_of(fn),
        'json': {
            'envelope': describe(),
            'rows': '行字段由上游接口决定 —— 先跑一次 `-f json` 看实际字段',
        },
    }
    if fam:
        out['family'] = fam
        # kinds 统一指"口径对象列表"; 名字列表用 kind_names, 数量用 kinds_count
        out['kind_names'] = kinds
        out['kinds_count'] = len(kinds)
        if kind:
            from prism.stock.bridge.ak_families import FAM
            spec = FAM[fam].get(kind)
            if spec:
                out['kind'] = {
                    'name': kind,
                    'interface': spec.get('n'),
                    'params': spec.get('p') or [],
                    'required': spec.get('r') or [],
                    'status': spec.get('st'),
                    'desc': spec.get('s'),
                }
                via = _via_of(spec.get('n'))
                if via:
                    out['kind']['dedicated'] = via
    return out


def _via_of(interface):
    """这个上游接口有没有更规整的专用命令入口"""
    if not interface:
        return None
    try:
        from prism.stock.bridge.ak_via import INTERFACE_VIA
    except Exception:
        return None
    cmd, flags = INTERFACE_VIA.get(interface, (None, {}))
    if not cmd:
        return None
    extra = ''.join(f' --{k}' for k in flags)
    return {
        'command': cmd,
        'usage': f'prism {cmd}{extra}',
        'note': '专用命令的字段做过筛选与单位折算, 结果更规整;'
                ' --kind 是原样透传上游字段',
    }


def kind_list(command, families):
    """某命令挂着的口径清单 (schema --list)"""
    fam = _family_of(command)
    if not fam or fam not in families:
        return {'command': command, 'family': fam or '', 'count': 0,
                'kinds': [], 'kinds_count': 0}
    rows = []
    for name, spec in sorted(families[fam].items()):
        rows.append({
            'name': name,
            'interface': spec.get('n'),
            'status': spec.get('st'),
            'desc': spec.get('s'),
            'params': spec.get('p') or [],
        })
    return {'command': command, 'family': fam, 'count': len(rows),
            'kinds': rows, 'kinds_count': len(rows)}


def all_schema(commands):
    """全部命令的目录"""
    rows = []
    for name in sorted(commands):
        fn = commands[name]
        doc = (fn.__doc__ or '').strip().splitlines()
        fam = _family_of(name)
        n_kinds = 0
        if fam:
            try:
                from prism.stock.bridge.ak_families import FAM
                n_kinds = len(FAM[fam])
            except Exception:
                n_kinds = 0
        rows.append({
            'command': name,
            'summary': doc[0] if doc else '',
            'params': [p['name'] for p in _params_of(fn)],
            'family': fam or '',
            'kinds_count': n_kinds,
        })
    return {'count': len(rows), 'commands': rows}
