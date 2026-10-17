import yfinance as yf

for ticker in ["AAPL", "TSLA"]:
    df = yf.download(ticker, period="3y")
    df.to_csv(f"{ticker}.csv", index=True)   # 这个会是正常 Date,Open,High...
