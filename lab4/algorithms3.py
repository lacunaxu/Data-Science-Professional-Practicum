import pandas as pd
import numpy as np
from statsmodels.tsa.arima.model import ARIMA

FILES = {
    "AAPL": "AAPL.csv",
    "TSLA": "TSLA.csv",
}

WEIGHTS = {
    "AAPL": 0.5,
    "TSLA": 0.5,
}

PRICE_COL = "Close"

SHORT_MA = 10
LONG_MA = 50
RSI_PERIOD = 14
RSI_BUY_MAX = 70
RSI_SELL_MIN = 30

ARIMA_ORDER = (2, 1, 0)
ARIMA_TRAIN_WINDOW = 120

INITIAL_CASH = 100000
RISK_FREE_RATE = 0.0
FEE_RATE = 0.0005

OUT_PORTFOLIO_CSV = "portfolio_multi_results.csv"
OUT_TRADELOG_CSV = "trade_log.csv"
OUT_FORECAST_CSV = "forecast_metrics.csv"


def normalize_weights(w):
    s = 0.0
    for k in w:
        s += float(w[k])
    if s <= 0:
        raise ValueError("WEIGHTS sum must be > 0")
    out = {}
    for k in w:
        out[k] = float(w[k]) / s
    return out


def load_stock_csv(path, price_col=PRICE_COL):
    # 跳过前两行：Price那行 + Ticker那行
    df = pd.read_csv(path, skiprows=2, header=None)

    # 现在 df 第一行应该是 ["Date", "", "", "", "", ""]
    # 把这一行丢掉
    df = df.iloc[1:].copy()

    # 强制列名：第0列是Date，其余是 Close/High/Low/Open/Volume
    df.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]

    # 转日期 & 排序
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date").set_index("Date")

    # 价格列你就用 Close（你的文件没有 Adj Close）
    if price_col != "Close":
        price_col = "Close"

    # 确保数值列是 float
    for c in ["Close", "High", "Low", "Open", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=[price_col])
    return df


def add_sma_rsi(df, price_col=PRICE_COL):
    out = df.copy()
    out["SMA_short"] = out[price_col].rolling(window=SHORT_MA).mean()
    out["SMA_long"] = out[price_col].rolling(window=LONG_MA).mean()

    delta = out[price_col].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.rolling(window=RSI_PERIOD).mean()
    avg_loss = loss.rolling(window=RSI_PERIOD).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["RSI"] = 100 - (100 / (1 + rs))
    out["RSI"] = out["RSI"].fillna(method="bfill")

    return out


def add_arima_one_step_forecast(df, price_col=PRICE_COL, order=ARIMA_ORDER, train_window=ARIMA_TRAIN_WINDOW):
    out = df.copy()
    prices = out[price_col].astype(float).values
    pred_next = [np.nan] * len(out)

    for t in range(train_window, len(out) - 1):
        train_series = prices[t - train_window: t]
        try:
            fit = ARIMA(train_series, order=order).fit()
            pred_next[t] = float(fit.forecast(steps=1)[0])
        except Exception:
            pred_next[t] = np.nan

    out["ARIMA_pred_next"] = pred_next
    return out


def generate_signals(df, price_col=PRICE_COL):
    out = df.copy()

    diff = out["SMA_short"] - out["SMA_long"]
    diff_prev = diff.shift(1)

    golden = (diff > 0) & (diff_prev <= 0)
    death = (diff < 0) & (diff_prev >= 0)

    arima_up = out["ARIMA_pred_next"] > out[price_col]
    arima_down = out["ARIMA_pred_next"] < out[price_col]

    out["Signal"] = 0
    buy = golden & (out["RSI"] < RSI_BUY_MAX) & arima_up
    sell = death & (out["RSI"] > RSI_SELL_MIN) & arima_down

    out.loc[buy, "Signal"] = 1
    out.loc[sell, "Signal"] = -1

    out["Position"] = 0
    position = 0
    for i in range(len(out)):
        s = int(out["Signal"].iloc[i])
        if s == 1:
            position = 1
        elif s == -1:
            position = 0
        out.iloc[i, out.columns.get_loc("Position")] = position

    return out


def backtest_with_tradelog(df, ticker, initial_cash, price_col=PRICE_COL, fee_rate=0.0005):
    out = df.copy()

    cash = float(initial_cash)
    shares = 0.0

    cash_hist = []
    shares_hist = []
    port_hist = []
    trades = []

    for i in range(len(out)):
        date = out.index[i]
        price = float(out[price_col].iloc[i])
        pos = int(out["Position"].iloc[i])

        if pos == 1 and shares == 0 and cash > 0:
            fee = cash * fee_rate
            buy_cash = cash - fee
            buy_shares = buy_cash / price
            shares = buy_shares
            cash = 0.0
            trades.append({
                "Date": date, "Ticker": ticker, "Action": "BUY",
                "Price": price, "Shares": buy_shares, "Fee": fee
            })

        if pos == 0 and shares > 0:
            sell_value = shares * price
            fee = sell_value * fee_rate
            cash = sell_value - fee
            trades.append({
                "Date": date, "Ticker": ticker, "Action": "SELL",
                "Price": price, "Shares": shares, "Fee": fee
            })
            shares = 0.0

        value = cash + shares * price
        cash_hist.append(cash)
        shares_hist.append(shares)
        port_hist.append(value)

    out["Cash"] = cash_hist
    out["Shares"] = shares_hist
    out["Portfolio"] = port_hist
    out["Strategy_Return"] = out["Portfolio"].pct_change()

    first_price = float(out[price_col].iloc[0])
    bh_shares = float(initial_cash) / first_price
    out["BuyHold_Portfolio"] = bh_shares * out[price_col].astype(float)

    return out, trades


def compute_metrics_from_portfolio(portfolio_series, initial_cash, risk_free_rate=0.0):
    s = portfolio_series.dropna().astype(float)
    final_value = float(s.iloc[-1])
    total_return = final_value / float(initial_cash) - 1.0

    daily = s.pct_change().dropna()
    years = (len(daily) / 252.0) if len(daily) > 0 else np.nan

    annualized = np.nan
    if years and years > 0:
        annualized = (final_value / float(initial_cash)) ** (1.0 / years) - 1.0

    sharpe = np.nan
    if daily.std() != 0 and not np.isnan(daily.std()):
        rf_daily = float(risk_free_rate) / 252.0
        excess = daily - rf_daily
        sharpe = (excess.mean() / excess.std()) * np.sqrt(252.0)

    return {
        "Final Value": final_value,
        "Total Return": total_return,
        "Annualized Return": annualized,
        "Sharpe Ratio": sharpe
    }


def forecast_mae_rmse(df, price_col=PRICE_COL, pred_col="ARIMA_pred_next"):
    actual_next = df[price_col].shift(-1)
    pred = df[pred_col]
    valid = pred.notna() & actual_next.notna()

    if int(valid.sum()) == 0:
        return {"MAE": np.nan, "RMSE": np.nan, "N": 0}

    err = (pred[valid] - actual_next[valid]).astype(float)
    mae = float(err.abs().mean())
    rmse = float(np.sqrt((err ** 2).mean()))
    return {"MAE": mae, "RMSE": rmse, "N": int(valid.sum())}


def main():
    weights = normalize_weights(WEIGHTS)

    per_ticker_results = {}
    all_trades = []
    forecast_rows = []

    for ticker in FILES:
        df = load_stock_csv(FILES[ticker], price_col=PRICE_COL)
        df = add_sma_rsi(df, price_col=PRICE_COL)
        df = add_arima_one_step_forecast(df, price_col=PRICE_COL)
        df = generate_signals(df, price_col=PRICE_COL)

        sub_cash = INITIAL_CASH * weights[ticker]
        df_bt, trades = backtest_with_tradelog(df, ticker, sub_cash, price_col=PRICE_COL, fee_rate=FEE_RATE)

        per_ticker_results[ticker] = df_bt
        all_trades.extend(trades)

        fm = forecast_mae_rmse(df_bt, price_col=PRICE_COL, pred_col="ARIMA_pred_next")
        forecast_rows.append({"Ticker": ticker, "MAE": fm["MAE"], "RMSE": fm["RMSE"], "N": fm["N"]})

    pd.DataFrame(forecast_rows).to_csv(OUT_FORECAST_CSV, index=False)

    combined = None
    for ticker in per_ticker_results:
        df_bt = per_ticker_results[ticker].copy()
        df_small = df_bt[[PRICE_COL, "Portfolio", "BuyHold_Portfolio"]].rename(columns={
            PRICE_COL: f"{ticker}_{PRICE_COL}",
            "Portfolio": f"{ticker}_Portfolio",
            "BuyHold_Portfolio": f"{ticker}_BuyHold"
        })
        combined = df_small if combined is None else combined.join(df_small, how="outer")

    combined = combined.sort_index()

    for ticker in per_ticker_results:
        combined[f"{ticker}_Portfolio"] = combined[f"{ticker}_Portfolio"].ffill()
        combined[f"{ticker}_BuyHold"] = combined[f"{ticker}_BuyHold"].ffill()

    portfolio_cols = []
    buyhold_cols = []
    for ticker in per_ticker_results:
        portfolio_cols.append(f"{ticker}_Portfolio")
        buyhold_cols.append(f"{ticker}_BuyHold")

    combined["Total_Portfolio"] = combined[portfolio_cols].sum(axis=1)
    combined["Total_BuyHold"] = combined[buyhold_cols].sum(axis=1)

    m_strategy = compute_metrics_from_portfolio(combined["Total_Portfolio"], INITIAL_CASH, risk_free_rate=RISK_FREE_RATE)
    m_bh = compute_metrics_from_portfolio(combined["Total_BuyHold"], INITIAL_CASH, risk_free_rate=RISK_FREE_RATE)

    combined.to_csv(OUT_PORTFOLIO_CSV)

    trade_df = pd.DataFrame(all_trades)
    if not trade_df.empty:
        trade_df["Date"] = pd.to_datetime(trade_df["Date"])
        trade_df = trade_df.sort_values(["Date", "Ticker", "Action"])
    trade_df.to_csv(OUT_TRADELOG_CSV, index=False)

    print("Done.")
    print("Strategy:", m_strategy)
    print("Buy&Hold:", m_bh)
    print("Saved:", OUT_PORTFOLIO_CSV, OUT_TRADELOG_CSV, OUT_FORECAST_CSV)


if __name__ == "__main__":
    main()
