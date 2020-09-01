import numpy as np
import datetime
from datetime import date
import dateutil.relativedelta
import datetime
from time import time, sleep
import yfinance as yf
from tqdm import tqdm

from .helpers import *

class Detector:
    def __init__(self, tickers):
        super().__init__()
        self.data = {}
        self.results = {}
        self.marketsClosed = marketsAreClosed()
        self.tickers = tickers

    def detect(self, ticker, relativeVolThreshold=2, volumeThreshold=200000):

        percentChangeYesterday = self.getPercentChangeNDaysAgo(ticker, days=0)

        outsideDay = self.isOutsideDay(ticker)

        if outsideDay:
            avgVolume = self.getAverageVolume(ticker)
            volume = self.getVolumeNDaysAgo(ticker, 0)
            relativeVol = volume / avgVolume
            if relativeVol > relativeVolThreshold and avgVolume > volumeThreshold:
                return {
                    'ticker': ticker,
                    'percent_change': percentChangeYesterday,
                    'volume': volume,
                    'relative_vol': relativeVol
                }
        else: 
            return False

    def detectEngulfingCandles(self, ticker, relativeVolThreshold=2, volumeThreshold=200000):
        percentChangeYesterday = self.getPercentChangeNDaysAgo(ticker, days=0)
        isEngulfingCandle = self.isEngulfingCandle(ticker)
        
        if isEngulfingCandle:
            try:
                avgVolume = self.getAverageVolume(ticker)
            except:
                return False
            volume = self.getVolumeNDaysAgo(ticker, 0)
            relativeVol = volume / avgVolume
            if relativeVol > relativeVolThreshold and avgVolume > volumeThreshold:
                return {
                    'ticker': ticker,
                    'percent_change': percentChangeYesterday,
                    'volume': volume,
                    'relative_vol': relativeVol
                }
        else: 
            return False

    def isEngulfingCandle(self, ticker):
        openPrice = self.getOpeningPriceNDaysAgo(ticker, days=0)
        openPrice2 = self.getOpeningPriceNDaysAgo(ticker, days=1)
        closePrice = self.getClosingPriceNDaysAgo(ticker, days=0)
        closePrice2 = self.getClosingPriceNDaysAgo(ticker, days=1)
        return (closePrice > openPrice2 and openPrice < closePrice2 and openPrice2 > closePrice2 and openPrice < closePrice) or (openPrice > closePrice2 and closePrice < openPrice2 and closePrice2 > openPrice2 and closePrice < openPrice)

    def isOutsideDay(self, ticker):
        openPrice = self.getOpeningPriceNDaysAgo(ticker, days=0)
        closePrice = self.getClosingPriceNDaysAgo(ticker, days=0)
        lowPrice = self.getLowPriceNDaysAgo(ticker, days=0)
        highPrice = self.getHighPriceNDaysAgo(ticker, days=0)

        closePrice2 = self.getClosingPriceNDaysAgo(ticker, days=1)
        openPrice2 = self.getOpeningPriceNDaysAgo(ticker, days=1)
        lowPrice2 = self.getLowPriceNDaysAgo(ticker, days=1)
        highPrice2 = self.getHighPriceNDaysAgo(ticker, days=1)

        return (closePrice > openPrice2 and openPrice < closePrice2 and openPrice2 > closePrice2 and openPrice < closePrice) or (openPrice > closePrice2 and closePrice < openPrice2 and closePrice2 > openPrice2 and closePrice < openPrice) and lowPrice < lowPrice2 and highPrice > highPrice2

    def isPositiveDay(self, openPrice, closePrice):
        return openPrice < closePrice

    def getPercentChangeNDaysAgo(self, ticker, days):
        dayClose = self.data[ticker]['Close'][-days-1]
        dayBeforeClose = self.data[ticker]['Close'][-days-2]
        return ((dayClose-dayBeforeClose)/dayBeforeClose) * 100

    def getAverageVolume(self, ticker):
        return np.mean(self.data[ticker]["Volume"])

    def getVolumeNDaysAgo(self, ticker, days):
        return self.data[ticker]['Volume'][-days-1]

    def getOpeningPriceNDaysAgo(self, ticker, days):
        return self.data[ticker]['Open'][-days-1]

    def getClosingPriceNDaysAgo(self, ticker, days):
        return self.data[ticker]['Close'][-days-1]

    def getHighPriceNDaysAgo(self, ticker, days):
        return self.data[ticker]['High'][-days-1]

    def getLowPriceNDaysAgo(self, ticker, days):
        return self.data[ticker]['Low'][-days-1]

    async def getDataDetectAndPrint(self):
        print('Getting all ticker data')
        num_analyzed = num_failed = 0
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=50)
        futures = []
        for ticker in self.tickers:
            futures.append(
                loop.run_in_executor(executor, self.getData, ticker))
        [await f for f in tqdm(asyncio.as_completed(futures), total=len(futures))]
        # await asyncio.gather(*futures)

        print("Analyzing all tickers")
        num_failed = 0
        for ticker in tqdm(self.data):
            try:
                self.detectPatterns(ticker)
                num_analyzed += 1
            except:
                num_failed += 1
        print(f"{num_analyzed} tickers analyzed with {num_failed} failures")

        self.renderOutput()
        self.sendEmail()

    def marketsAreClosed(self):
        now = datetime.datetime.now()
        # monday is 0 sunday is 6 
        day = now.weekday()
        hour = now.hour
        minute = now.minute
        if day > 4: # is weekend
            return True
        elif hour < 8 or (hour == 8 and minute < 30) or hour > 14: # is earlier than 8:30am or is later than 3pm
            return True
        else: # weekday but markets are closed
            return False

    def insertResult(self, pattern, ticker, data):
        try:
            self.results[pattern][ticker] = data
        except:
            self.results[pattern] = {}
            self.results[pattern][ticker] = data

    def detectPatterns(self, ticker):
        outsideDayData = self.detectOutsideDay(ticker)
        engulfingCandleData = self.detectEngulfingCandles(ticker)
        if outsideDayData:
            self.insertResult('Outside Day', ticker, outsideDayData)
        elif engulfingCandleData:
            self.insertResult('Engulfing Candle', ticker, engulfingCandleData)

    def addOutputData(self, data):
        self.outputString += f"""Ticker: {data['ticker']}
Change: { (data['percent_change']):.2f}%
Volume: {data['volume']}
RelativeVol: {data['relative_vol']:.2f}

"""

    def renderOutput(self):
        for pattern in self.results:
            self.outputString +=(f"\nTickers matching '{pattern}' pattern\n\n")
            for ticker in self.results[pattern]:
                data = self.results[pattern][ticker]
                self.addOutputData(data)

    def sendEmail(self):
        if self.outputString == '':
            self.outputString = 'No patterns detected today'
        email = MIMEText(self.outputString)
        current_time = datetime.datetime.now()
        email['Subject'] = f'Pattern Detector Report ({current_time.strftime("%m/%d/%Y")})'
        email['From'] = f'Pattern Detector <{self.from_email}>'
        email['To'] = COMMASPACE.join(self.to_email)

        email_password = self.getEmailPass()

        s = smtplib.SMTP_SSL('smtp.gmail.com', port=465)
        s.login(self.from_email, email_password)
        s.sendmail(self.from_email, self.to_email, email.as_string())
        s.quit()

    def getEmailPass(self):
        try:
            return os.environ['EMAIL_PASS']
        except:
            password_file = open('app_pass.txt', 'r')
            password = password_file.read()
            password_file.close()
            return password

    async def main(self):
        start = datetime.datetime.now()
        await self.getDataDetectAndPrint()
        print(f'Runtime (HH:MM:SS.SSSSSS): {datetime.datetime.now()-start}')


if __name__ == "__main__":
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(OutsideDayDetector().main())
    loop.close()