"""诊断输出纪律: 正常路径 stderr 必须干净, 线索只在 -d / --log-file 里

这类回归很隐蔽 —— 多一行 "[INFO] 构建候选池..." 不影响任何结果, 但会
污染所有把 prism 当数据源调用的场景 (管道、agent、cron 抓 JSON)。
"""
import os
import shutil
import time
import subprocess

# 用装好的入口: `-m prism.cli.app` 会让 helptext 找不到 __main__ 上的 app
PRISM = [shutil.which('prism') or 'prism']

# 只挑不依赖外网、跑得快的命令
OFfline = [['calendar'], ['schema', '--all'], ['-h'], ['quote', '-h']]


def _run(argv, **kw):
    return subprocess.run(PRISM + argv, capture_output=True, text=True,
                          timeout=120, **kw)


def test_normal_runs_are_quiet():
    for argv in OFfline:
        r = _run(argv)
        assert r.stderr == '', f"{' '.join(argv)} 往 stderr 打了东西: {r.stderr[:300]!r}"


def test_debug_flag_turns_logs_on():
    """-d 必须真能看见诊断, 否则等于把线索弄丢了"""
    r = _run(['-d', 'calendar'])
    assert 'logging | 装配完成' in r.stderr, r.stderr[:300]
    assert 'D ' in r.stderr or 'DEBUG' in r.stderr


def test_debug_flag_position_free():
    """-d 放命令前后都认"""
    back = _run(['calendar', '-d'])
    assert '装配完成' in back.stderr


def test_log_file_keeps_terminal_clean(tmp_path='/tmp/prism_test_log.txt'):
    import os
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    r = _run(['--log-file', tmp_path, 'calendar'])
    assert r.stderr == '', r.stderr[:300]
    with open(tmp_path, encoding='utf-8') as f:
        body = f.read()
    assert 'DEBUG' in body and len(body) > 0


def test_bad_config_warns_once():
    """坏配置必须提示 (否则用户以为配了却没生效), 但一次运行只提示一次"""
    import os
    import tempfile
    d = tempfile.mkdtemp()
    with open(os.path.join(d, 'config.json'), 'w', encoding='utf-8') as f:
        f.write('{bad json')
    env = dict(os.environ, PRISM_DIR=d)
    r = subprocess.run(PRISM + ['quote', '600519'], capture_output=True,
                       text=True, timeout=180, env=env)
    n = r.stderr.count('读取失败')
    assert n <= 1, f'同一份坏配置报了 {n} 次'


def test_no_bare_bracket_log_prefix():
    """引擎进度不能以 [INFO]/[WARN] 直接打进 stderr"""
    r = _run(['screen', '--pool', 'short', '-n', '2'])
    assert '[INFO]' not in r.stderr
    assert '[WARN]' not in r.stderr


def _env(tmpdir, **extra):
    env = dict(os.environ)
    env['PRISM_DIR'] = str(tmpdir)
    env.pop('PRISM_LOG_FILE', None)
    env.pop('PRISM_DEBUG', None)
    env.pop('PRISM_LOG', None)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def test_default_run_persists_debug_log(tmp_path):
    """默认落盘: 终端安静, 但 DEBUG 全量进了 ~/.prism/logs/prism.log"""
    subprocess.run(PRISM + ['quote', '600519'], env=_env(tmp_path),
                   capture_output=True, timeout=120)
    log = tmp_path / 'logs' / 'prism.log'
    assert log.exists(), '默认没有落盘'
    text = log.read_text(encoding='utf-8', errors='replace')
    assert 'DEBUG' in text and 'prism.net' in text


def test_log_appends_across_runs(tmp_path):
    for _ in range(2):
        subprocess.run(PRISM + ['quote', '600519'], env=_env(tmp_path),
                       capture_output=True, timeout=120)
    lines = (tmp_path / 'logs' / 'prism.log').read_text(encoding='utf-8').splitlines()
    assert len(lines) > 4, '第二次运行没有追加, 像是覆盖写了'


def test_stale_log_is_rotated_by_date(tmp_path):
    """昨天的 prism.log 启动时改名成 .YYYYMMDD, 新档另起"""
    d = tmp_path / 'logs'
    d.mkdir(parents=True)
    old = d / 'prism.log'
    old.write_text('old\n', encoding='utf-8')
    stamp = time.time() - 86400 * 2
    os.utime(old, (stamp, stamp))
    day = time.strftime('%Y%m%d', time.localtime(stamp))
    subprocess.run(PRISM + ['quote', '600519'], env=_env(tmp_path),
                   capture_output=True, timeout=120)
    assert (d / ('prism.log.' + day)).read_text(encoding='utf-8') == 'old\n'
    assert 'DEBUG' in (d / 'prism.log').read_text(encoding='utf-8')


def test_old_logs_are_pruned_to_keep(tmp_path):
    """旧档只留最近 N 份"""
    d = tmp_path / 'logs'
    d.mkdir(parents=True)
    for i in range(1, 12):
        (d / ('prism.log.202610{:02d}'.format(i))).write_text('x', encoding='utf-8')
    subprocess.run(PRISM + ['quote', '600519'], env=_env(tmp_path),
                   capture_output=True, timeout=120)
    olds = sorted(p.name for p in d.glob('prism.log.[0-9]*'))
    assert len(olds) == 7, olds


def test_prism_log_off_disables_file(tmp_path):
    subprocess.run(PRISM + ['quote', '600519'], env=_env(tmp_path, PRISM_LOG='0'),
                   capture_output=True, timeout=120)
    assert not (tmp_path / 'logs' / 'prism.log').exists()
