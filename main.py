
import argparse
from calendar import format
from json import JSONEncoder
from pprint import pprint;
import requests as req;
from nsetools import nse
from collections import  namedtuple;
import schedule;
import sys;
import time;
import os;
import logging
import datetime;
import json;
from dotmap import DotMap;
import pickle


# logging.addHandler()

head = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36",
}



if hasattr(time, 'tzset'):
    os.environ['TZ'] = 'Asia/Kolkata'
    time.tzset()


# Getting fno lot size
fno = nse.Nse()
fno_lot = fno.get_fno_lot_sizes(as_json=False);

call="CE"
put="PE"

RECORDS, FILTERED = 0,0;

INDICES = ["NIFTY","BANKNIFTY","FINNIFTY"]

INDICES_URL = "https://www.nseindia.com/api/option-chain-indices"

EQUITY_URL = "https://www.nseindia.com/api/option-chain-equities"

def tuple_arg(strings):
    mapped_int = map(int, strings.split(","))
    return tuple(mapped_int)

def str_upper(string):
    return string.upper();

def tuple_strike(string):
    string = string.replace("(","")
    string = string.replace(")","")
    pe_ce = list(map(float, string.split(",")))
    return tuple(pe_ce[:2]),tuple(pe_ce[2:])

parser = argparse.ArgumentParser();

parser.add_argument("--stock", type= str_upper ,default="BANKNIFTY", help="number of epochs of training")
parser.add_argument("--trade", type= tuple_arg, default=None, help="number of epochs of training")
parser.add_argument("--refresh", type=int ,default=5, help="number of epochs of training")
parser.add_argument("--profit", type=int ,default=2000, help="number of epochs of training")
parser.add_argument("--expiry", type=int ,default=0, help="number of epochs of training")
parser.add_argument("--print" , type=bool ,default=False, help="number of epochs of training")
parser.add_argument("--skip_time" , type=bool ,default=False, help="number of epochs of training")
parser.add_argument("--open_interest" , type=bool ,default=True, help="number of epochs of training")
parser.add_argument("--pick" ,type=str, default=None, help="number of epochs of training")
parser.add_argument("--init_trade" ,type=tuple_strike, default=None, help="number of epochs of training")

cmd_arg = parser.parse_args();

# a = os.system("sh cmd.sh")

log = f"./logs/{cmd_arg.stock}"

if not os.path.exists(log):
    os.makedirs(log)


class NseConnection:
    def __init__(self):
        self.requestType = "python";
        try:
            ses = req.Session()
            ses.get('https://www.nseindia.com',headers=head, timeout = 5);
            self.requestType = "python";
        except:
            self.requestType = "curl";

        pass
    def get_optionchain(self, stock):
        # print(self.requestType)
        try:
            if(self.requestType == "python"):
                ses = req.Session()
                ses.get('https://www.nseindia.com',headers=head, timeout = 5)

                if stock in INDICES:
                    url = INDICES_URL
                else:
                    url = EQUITY_URL
                data = ses.get(url, params={'symbol':stock}, headers = head)
                self.response = json.loads(data.text, object_hook=lambda d: DotMap(d))
            else:
                if stock in INDICES:
                    url = INDICES_URL+"?symbol="+stock
                else:
                    url = EQUITY_URL+"?symbol="+stock
                os.system(f"sh cmd.sh {url}")
                with open("data.json", "r") as read_file:
                    try:
                        data = json.load(read_file)
                        self.response = json.loads(json.dumps(data), object_hook=lambda d: DotMap(d))
                    except:
                        self.print(f"Decoding error {data}")
            return self.response
        except:
            self.print(f"Resonse error {self.requestType}")

    def print(self,txt):
        if cmd_arg.print == True:
            print(txt);
        logging.info(txt)


class ObjectFactory:

    def __init__(self):
        pass;

    def save_object(self,obj,name = None):
        now = datetime.datetime.now()
        path = "strangle-data/" + obj.stock + "/";
        if not os.path.exists(path):
            os.makedirs(path)
        if(name == None):
            nameStamp = obj.stock + "-" + obj.time_stamp+ ".pck"
        else:
            nameStamp = name or "latest.pck";

        # used to remove latest file

        if name == "squareoff.pck" and os.path.exists(path+"latest.pck"):
            os.remove(path+"latest.pck");
        with open(path+nameStamp,"wb") as fd:
            pickle.dump(obj,fd);
        return nameStamp;

    def load_object(self,name = None,stock="NIFTY" ):
        name = name or "latest";
        if ".pck" not in name:
            name += ".pck"
        path = f"strangle-data/{stock}/{name}"
        try:
            with open(path,"rb") as fd:
                data = pickle.load(fd);
                now = datetime.datetime.now().date();
                exp = datetime.datetime.strptime(data.expiry, '%d-%b-%Y').date()
                if exp < now:
                    return None
                return data;
        except:
            # print("not such dir")
            # logging.info("not such dir")
            return None;

class OptionChain():
    def __init__(self,stock, expiry = None, min_profit = 2000, adjustment_percent= 0.5, straddle_adjustment = 0.1, get_premium_percent = 0.9):
        self.stock = stock;
        self.lot_size = fno_lot[self.stock]
        self.adjustment_percent = adjustment_percent
        self.straddle_adjustment = straddle_adjustment
        self.get_premium_percent = get_premium_percent
        self.min_profit = min_profit
        now = datetime.datetime.now()
        self.time_stamp = now.strftime("%Y-%m-%d_%H-%M-%S");
        self.straddle_point = DotMap();
        logging.basicConfig(filename = f"logs/{self.stock}/{self.stock}-{self.time_stamp}.log",format = '%(message)s', level=logging.INFO)
        # self.fd = open(f"strangle-data/trade-data/{self.time_stamp}","a");

        self.loader = ObjectFactory();

        self.get_optionchain();
        self.set_expiry(expiry);
        self.seggrigate_pe_ce();

   
    def get_optionchain(self):
        try:
            self.response = nse_con.get_optionchain(self.stock)
            self.records = self.response.records
            self.filtered = self.response.filtered
            self.ltp = self.records.underlyingValue;
        except:
            self.print("No Data")


    def set_expiry(self,expiry):
        if(expiry == None):
            self.expiry = self.records.expiryDates[0];
        else:
            self.expiry = self.records.expiryDates[expiry];

    def seggrigate_pe_ce(self):
        PE = [];
        CE = [];
        for data in self.records.data:
            if(put in  data):
                if(self.expiry == data.expiryDate):
                    data.PE.lastPrice = data.PE.bidprice
                    PE.append(data.PE);
            if(call in  data):
                if(self.expiry == data.expiryDate):
                    data.CE.lastPrice = data.CE.bidprice
                    CE.append(data.CE);
        self.pe_list = PE;
        self.ce_list = CE;

    def get_pe_close(self,value , before = False):
        for (i,item) in enumerate(self.pe_list):
            if(item.lastPrice > value):
                if(not before):
                    return item;
                else:
                    return self.pe_list[i-1]

    def get_ce_close(self,value, before = False):
        cList = list(reversed(self.ce_list))
        for (i,item) in enumerate(cList):
            if(item.lastPrice > value):
                if(not before):
                    return item;
                else:
                    return cList[i-1]

    def trade_setup(self, pe_value = 30, ce_value = 30, _pe = None, _ce = None):
        if(_pe and _ce):
            pe = _pe
            ce = _ce
        else:
            pe = self.get_pe_close(pe_value);
            ce = self.get_ce_close(ce_value);
        
        if(pe.strikePrice >= ce.strikePrice):
        #     Need to convert it to straddle
            ce = self.get_ce_strike(pe.strikePrice);
            self.straddle_point.pe = pe
            self.straddle_point.ce = ce
            
        self.profit = 0;
        traded_price = {
            "pe": pe,
            "ce": ce,
            "expiry": self.expiry,
            "ltp": self.ltp
        }

        self.traded_price = DotMap(traded_price)
        self.entry_price = self.traded_price;

        return ;
    
    def trade_OI(self):
        
        pe = max(self.pe_list,key = lambda d: d.openInterest)
        ce = max(self.ce_list,key = lambda d: d.openInterest)
        self.trade_setup(_pe = pe, _ce = ce)
    
    def init_trade(self,_pe,_ce):
        pe_strike,pe_value = _pe
        ce_strike,ce_value = _ce
        
        pe = self.get_pe_strike(pe_strike).copy();
        ce = self.get_ce_strike(ce_strike).copy();
        
        pe.lastPrice = pe_value
        ce.lastPrice = ce_value
        
        self.trade_setup(_pe=pe,_ce=ce)
        
    def get_pe_strike(self,stirke):
        for item in self.pe_list:
            if(item.strikePrice == stirke):
                return item;

    def get_ce_strike(self,stirke):
        for item in self.ce_list:
            if(item.strikePrice == stirke):
                return item;

    def update_option(self):
        # Get Option chain data
        now = datetime.datetime.now()
        #print("Current date and time : ")
        #print(now.strftime("%Y-%m-%d %H:%M:%S"))

        self.time_stamp = now.strftime("%Y-%m-%d_%H-%M-%S");
        self.print(f"Current date and time : {now.strftime('%Y-%m-%d %H:%M:%S')}")

        self.get_optionchain();

        # Seperate PE and CE values
        self.seggrigate_pe_ce();

        try:

            # Get the current price of PE
            pe = self.get_pe_strike(self.traded_price.pe.strikePrice).copy();

            # Get the current price of CE
            ce = self.get_ce_strike(self.traded_price.ce.strikePrice).copy();

            #printpe.strikePrice,pe.lastPrice)
            self.print(f"{pe.strikePrice} {pe.lastPrice}")
            #printce.strikePrice,ce.lastPrice)
            self.print(f"{ce.strikePrice} {ce.lastPrice}")


            profit = self.get_profit(pe.askPrice, ce.askPrice);

            if(profit > self.min_profit):

                #print"Acheived Target");
                self.print("Acheived Target");
                self.square_off(pe,ce)

            else:

                self.check_adjustments(pe,ce);
                # schedule.clear(self.stock)

        except:
            #print"No Stirke Values")
            e = sys.exc_info()
            self.print("No Stirke Values")
            self.print(e)

    def square_off(self,pe,ce):
        traded_price = self.traded_price.copy();
        traded_price['pe'] = pe
        traded_price['ce'] = ce
        self.loader.save_object(self,"squareoff.pck")
        self.exit_price = DotMap(traded_price)
        schedule.clear(self.stock)


    def check_adjustments(self,_pe, _ce):

        current_time = datetime.datetime.now().time();
        strangle_time = datetime.time(15,25);
        # How much percent we need to adjust
        adjustment_percent = self.adjustment_percent;

        # At end of date we need to convert change adjustment to 80%
        if( current_time > strangle_time):
            adjustment_percent = 0.8;

        # Check Straddle 
        if(self.traded_price.pe.strikePrice == self.traded_price.ce.strikePrice):
            total = self.straddle_point.pe.lastPrice + self.straddle_point.ce.lastPrice;
            #print"Straddle")
            self.print("Straddle")
            
            if((_pe.lastPrice + _ce.lastPrice) > (total + (total * self.straddle_adjustment))):
                #print"Straddle > than",_pe.lastPrice + _ce.lastPrice,total);
                self.print(f"Straddle > than,{_pe.lastPrice + _ce.lastPrice,total}");
                self.get_profit(_pe.askPrice,_ce.askPrice);
                self.square_off(_pe,_ce);
                # exit(0)
                return;
            return ;

        #   check if pe premium is less than half; (PE in profit need to move farword)
        if(_ce.lastPrice * adjustment_percent > _pe.lastPrice):
            #print"Need to square off PE");
            self.print("Need to square off PE");
            self.profit += self.traded_price.pe.lastPrice - _pe.lastPrice;
            percent_premium = self.get_premium_percent;
            while True:
                pe = self.get_pe_close( _ce.lastPrice * percent_premium, before= True);
                if(pe.strikePrice >= _ce.strikePrice or pe.lastPrice <= _ce.lastPrice*percent_premium or percent_premium < 0):
                    break;
                else:
                    percent_premium -= 0.05
            # Checking if PE exceeded CE
            if(pe.strikePrice >= self.traded_price.ce.strikePrice):
                # Becomes Straddle
            
                self.print("Making it Straddle")
                pe = self.get_pe_strike(self.traded_price.ce.strikePrice);
                # Need to store the current straddle values
                self.straddle_point.ce = _ce.copy();
                self.straddle_point.pe = pe.copy();
                
            self.update_pe(pe);
            return;

        if(_pe.lastPrice * adjustment_percent > _ce.lastPrice):
            #print"Need to square off CE");
            self.print("Need to square off CE");
            self.profit += self.traded_price.ce.lastPrice - _ce.lastPrice ;
            percent_premium = self.get_premium_percent;
            while True:

                ce = self.get_ce_close( _pe.lastPrice * percent_premium, before= True)
                if(ce.strikePrice >= _pe.strikePrice or ce.lastPrice <= _pe.lastPrice * percent_premium or percent_premium < 0):
                    break;
                else:
                    percent_premium -= 0.05;

            if(ce.strikePrice <= self.traded_price.pe.strikePrice):
                # Becomes Straddle
                
                self.print("Making it Straddle")
                ce = self.get_ce_strike(self.traded_price.pe.strikePrice)
                # Need to store the current straddle values
                self.straddle_point.pe = _pe.copy();
                self.straddle_point.ce = ce.copy();
                
            self.update_ce(ce);
            return


    def update_pe(self,pe):
        traded_price = self.traded_price;
        traded_price['pe'] = pe;

        self.traded_price = DotMap(traded_price)

    def update_ce(self,ce):
        traded_price = self.traded_price;
        traded_price['ce'] = ce;

        self.traded_price = DotMap(traded_price)


    def get_reliased_profit(self):
        #print"Profit\t{:.2f}".format(self.profit* self.lot_size))
        self.print("Profit\t{:.2f}".format(self.profit* self.lot_size))

    def get_profit(self, pe_value, ce_value):

        profit = 0;
        profit += self.traded_price.pe.lastPrice -  pe_value ;
        profit += self.traded_price.ce.lastPrice - ce_value ;
        # Adding existing profit
        profit += self.profit;

        profit *= self.lot_size;

        if(profit > 0 ):
            #print"Profit\t{:.2f}".format(profit))
            self.print("Profit\t{:.2f}".format(profit))
        else:
            #print"Loss\t{:.2f}".format(profit))
            self.print("Loss\t{:.2f}".format(profit))

        return profit;

    def set_pe_ce(self,pe_value,ce_value):

        pe = self.traded_price.pe;
        pe['lastPrice'] = pe_value;
        pe =  DotMap(pe)

        ce = self.traded_price.ce;
        ce['lastPrice'] = ce_value;
        ce =  DotMap(ce)

        traded_price = {
            "pe": pe,
            "ce": ce,
            "expiry": self.expiry,
            "ltp": self.ltp
        }

        self.traded_price = DotMap(traded_price);


    #   schedule task

    def print(self,txt):
        if cmd_arg.print == True:
            print(txt);
        logging.info(txt)


    def get_update(self,save):
        # #printsave)
        self.update_option();
        current_time = datetime.datetime.now().time();
        market_time = datetime.time(15,30);
        if current_time > market_time and not cmd_arg.skip_time:
            self.loader.save_object(self,"latest.pck");
            schedule.clear(self.stock)
        if save:
            self.loader.save_object(self)

    def task_schedule(self, t_seconds = 5 ,save = False):

        schedule.every(t_seconds).seconds.do(self.get_update,save).tag(self.stock);

def main():
    
    global nse_con,loader;

    loader = ObjectFactory();

    nse_con = NseConnection();
    
    stock = loader.load_object(name = cmd_arg.pick,stock = cmd_arg.stock)
    
    if stock:
        logging.basicConfig(filename = f"logs/{stock.stock}/{stock.stock}-{stock.time_stamp}.log",format = '%(message)s', level=logging.INFO)
    else:
        stock = OptionChain(stock=cmd_arg.stock, expiry=cmd_arg.expiry, min_profit= cmd_arg.profit)
        if cmd_arg.trade:
            stock.trade_setup(*cmd_arg.trade);
        elif cmd_arg.init_trade:
            stock.init_trade(*cmd_arg.init_trade)
        elif cmd_arg.open_interest:
            stock.trade_OI();
    
    stock.task_schedule(cmd_arg.refresh)

    try:
        while True:
            schedule.run_pending();
            if(not schedule.jobs):
                break;
            time.sleep(1);
    except:
        loader.save_object(stock,"error.pck")
        logging.exception("Error ")
    
    
    # d = nse_con.get_optionchain("NIFTY")
    
    
    
if __name__ == '__main__':
    main()
