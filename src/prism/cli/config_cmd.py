"""`prism config` —— 读写 ~/.prism/config.json

net 层十几处错误提示都指向 `prism config set/unset`, 但扁平化时这个命令没跟
过来, 于是"让用户改配置"的告示指向一条不存在的命令。这里补上, 并且:

- 键表与校验都从 core.config_schema 派生 (单一来源, 不另写一份)
- 只写用户文件里的键, 不把默认值整份糊进去 —— 否则以后改默认值会被旧文件盖住
- set 当场校验, 非法值直接拒并给出合法范围
"""

import json
import os

import typer

from prism.core.config_schema import cli_table, validate
from prism.net.proxy.store import CONFIG_PATH, load_config, unknown_keys

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  rich_markup_mode=None, pretty_exceptions_enable=False,
                  help='查看/修改 ~/.prism/config.json')


def _raw():
    """配置文件原文 (不含默认值), 失败当空"""
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(raw):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def _show(v):
    return json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v


@app.command('list')
def config_list(mark: bool = typer.Option(False, '--changed',
                                          help='只列显式设置过的键')):
    """列出全部配置键 (标 * 的是配置文件里写死的)"""
    raw, eff = _raw(), load_config()
    width = max(len(k) for k in cli_table())
    for k, (desc, hint, _typ) in cli_table().items():
        explicit = k in raw
        if mark and not explicit:
            continue
        val = raw.get(k) if explicit else eff.get(k)
        flag = '*' if explicit else ' '
        line = f'{flag} {k:<{width}} {_show(val)}'
        if desc:
            line += f'   {desc}'
        print(line)
    orphans = unknown_keys()
    if orphans:
        print('\n没人认的键 (会被忽略, 删掉即可): ' + ', '.join(orphans))
    print(f'\n配置文件 {CONFIG_PATH}   (* = 已显式设置)')


@app.command('get')
def config_get(key: str = typer.Argument(..., help='键名')):
    """读一个键的当前生效值"""
    if key not in cli_table():
        raise typer.BadParameter(f'未知配置键: {key}')
    val = _raw().get(key, load_config().get(key))
    print(_show(val))


@app.command('set')
def config_set(key: str = typer.Argument(..., help='键名'),
               value: str = typer.Argument(..., help='值')):
    """写一个键 (当场校验)"""
    ok, out = validate(key, value)
    if not ok:
        raise typer.BadParameter(str(out))
    raw = _raw()
    raw[key] = out
    _save(raw)
    print(f'{key} = {_show(out)}')


@app.command('unset')
def config_unset(key: str = typer.Argument(..., help='键名')):
    """删掉一个键, 回到默认值"""
    raw = _raw()
    if key not in raw:
        print(f'{key} 本来就没设')
        return
    raw.pop(key)
    _save(raw)
    print(f'已删 {key}')


@app.command('pass')
def config_pass(user: str = typer.Argument(..., help='引用名: user@host[:port]'),
                password: str = typer.Argument(..., help='代理密码')):
    """写入代理密码 (密文存 config.json 的 proxy_auth)"""
    from prism.core.secrets_store import store_password
    created = store_password(user, password)
    print(f'{"已写入" if created else "已更新"} {user} 的密码 (密文)')


@app.command('unpass')
def config_unpass(user: str = typer.Argument(..., help='引用名')):
    """删掉某个代理密码"""
    from prism.core.secrets_store import drop_password
    print(f'已删 {user} 的密码' if drop_password(user) else f'{user} 没有密码记录')
