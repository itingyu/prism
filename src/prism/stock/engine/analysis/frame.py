"""最小 DataFrame 替身 (numpy 后端)

为什么不用 pandas: 本机 `import pandas` 要 2.8s (numpy 只要 0.5s), 而技术指标
真正需要的只是"列 + 末两行 + rolling 均值"这几件事。analyze / 选股池每次
调用都要付这笔启动税, 换成自带 Frame 后少 2 秒多。

pandas 仍然留在真正需要表格的地方: bridge/http 的表格渲染、excel 导出、
akshare/efinance 的 DataFrame 透传。

对外只暴露:
    build(rows) -> Frame      # 从 list[dict] 建
    Frame                      # df[col] / df['x'] = ... / df.iloc[i] / len(df)
"""
import numpy as np

__all__ = ['Frame', 'build', 'isna']


def isna(v) -> bool:
    """pandas.isna 的等价判断 (None / NaN / 缺失都算)"""
    if v is None:
        return True
    try:
        return bool(np.isnan(v))
    except (TypeError, ValueError):
        return False


class Series:
    """列的序列视图: 支持 .tail(n).mean() / .max() / .iloc[-1] 等常用写法"""

    __slots__ = ('values',)

    def __init__(self, values):
        self.values = list(values)

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, i):
        return self.values[i]

    def __array__(self, dtype=None):
        return np.array(self.values, dtype=dtype or float)

    @property
    def iloc(self):
        return self

    def tail(self, n):
        n = max(int(n), 0)
        return Series(self.values[-n:] if n else [])

    def _valid(self):
        return [v for v in self.values if not isna(v)]

    def max(self):
        v = self._valid()
        return max(v) if v else None

    def min(self):
        v = self._valid()
        return min(v) if v else None

    def mean(self):
        v = self._valid()
        return sum(v) / len(v) if v else float('nan')


class Row(dict):
    """df.iloc[i] 的行: 支持 row['close'] 与 row.get('ma5')"""


class _ILoc:
    __slots__ = ('_f',)

    def __init__(self, frame):
        self._f = frame

    def __getitem__(self, idx):
        f = self._f
        if isinstance(idx, slice):
            return [f._row(i) for i in range(*idx.indices(len(f)))]
        i = idx if idx >= 0 else len(f) + idx
        return f._row(i)


class Frame:
    """列式数据框: 列是 list, 行是 dict 视图"""

    __slots__ = ('columns', '_data')

    def __init__(self, columns=None, data=None):
        self.columns = list(columns or [])
        data = data or {}
        self._data = {c: list(data.get(c, [])) for c in self.columns}
        for c, v in data.items():                 # 允许调用方塞额外列
            if c not in self.columns:
                self.columns.append(c)
            self._data[c] = list(v)

    # ── 基本协议 ────────────────────────────────────────────────
    def __len__(self):
        return max((len(v) for v in self._data.values()), default=0)

    @property
    def empty(self) -> bool:
        return len(self) == 0

    @property
    def iloc(self):
        return _ILoc(self)

    def __getitem__(self, col):
        return Series(self._data[col])

    def __setitem__(self, col, values):
        self._data[col] = list(values)
        if col not in self.columns:
            self.columns.append(col)

    def __contains__(self, col):
        return col in self._data

    def __repr__(self):                          # pragma: no cover - 调试用
        return f'<Frame rows={len(self)} cols={len(self.columns)}>'

    # ── 常用操作 ────────────────────────────────────────────────
    def copy(self):
        return Frame(list(self.columns), {c: list(v) for c, v in self._data.items()})

    def tail(self, n):
        n = max(int(n), 0)
        return Frame(list(self.columns),
                     {c: list(v)[-n:] if n else [] for c, v in self._data.items()})

    def to_rows(self):
        return [self._row(i) for i in range(len(self))]

    def _row(self, i):
        return Row({c: (v[i] if i < len(v) else None) for c, v in self._data.items()})


def build(rows) -> Frame:
    """list[dict] → Frame (列按首次出现顺序, 缺列补 None)"""
    rows = list(rows or [])
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    data = {c: [r.get(c) for r in rows] for c in cols}
    return Frame(cols, data)
