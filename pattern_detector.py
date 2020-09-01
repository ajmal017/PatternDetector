import numpy as np
import datetime
from datetime import date
import dateutil.relativedelta
import datetime
from time import time, sleep
import yfinance as yf
from tqdm import tqdm
import sys
import os
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from patterndetector.detector import *
from stocklist import NasdaqController


class OutsideDayDetector(Detector):
    def __init__(self):
        super().__init__()
        self.data = {}
        self.results = {}
        self.outputString = ""
        self.marketsClosed = self.marketsAreClosed()
        StocksController = NasdaqController(True)
        self.tickers = StocksController.getList()

        parser = argparse.ArgumentParser()
        parser.add_argument('from_email', help='email address to send from')
        parser.add_argument('to_email', nargs='*', help='email address to send to')
        parser.add_argument('--patterns', nargs='*', help='patterns to analyze')
        args = parser.parse_args()
        self.to_email = args.to_email
        self.from_email = args.from_email
        if args.patterns:
            self.patterns = args.patterns
        else:
            self.patterns = ['outsideday']

    def isPositiveDay(self, openPrice, closePrice):
        return openPrice < closePrice

    def getPercentChangeNDaysAgo(self, ticker, days):
        dayClose = self.data[ticker]['Close'][-days-1]
        dayBeforeClose = self.data[ticker]['Close'][-days-2]
        return ((dayClose-dayBeforeClose)/dayBeforeClose) * 100

    def pullAverageVolume(self, ticker):
        return yf.Ticker(ticker).info['averageVolume']

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

    def getData(self, ticker):
        data = None
        if '$' in ticker or '.' in ticker:
            return
        try:
            delay = 1
            sys.stdout = open(os.devnull, "w")
            data = yf.Ticker(ticker).history(period="4mo")
            while data.empty and delay < 16:
                sleep(delay)
                delay *= 2
                data = yf.Ticker(ticker).history(period="4mo")
            sys.stdout = sys.__stdout__
            if not data.empty and len(data) > 1:
                if not self.marketsClosed:
                    data = data[:-1]
                self.data[ticker] = data
        except:
            pass

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