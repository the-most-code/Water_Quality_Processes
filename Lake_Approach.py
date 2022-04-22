"""
Created on 1/26/2022

@author: Tano_E
"""

import pandas as pd
import scipy
from scipy.stats.mstats import gmean
import math
from math import sqrt
from math import exp
import numpy as np

# import os.path
import os
import shutil
import sqlite3
import xlsxwriter
import openpyxl

import bokeh
from bokeh.models import ColumnDataSource #CategoricalColorMapper
from bokeh.io import save, output_file, show
from bokeh.plotting import figure
from bokeh.models import HoverTool, Legend
from bokeh.transform import factor_cmap
import bokeh.palettes as bkplt
from bokeh.io import save, output_file
from bokeh.layouts import column, row
from bokeh.models import Range1d
from bokeh.models import DatetimeTicker
from bokeh.models import Panel, Tabs
from bokeh.models import DatetimeTickFormatter
from statistics import mean, median, mode, stdev
from scipy.stats.mstats import gmean
from bokeh.io import curdoc

# this class has waterbody characteristics
class Waterbody:
    def __init__(self, wbid, start_yr, analyte):
        self.wbid = wbid
        self.start_yr = start_yr
        self.analyte = analyte

# waterbodies have data
class sourceData(Waterbody):
    def __init__(self, wbid, start_yr, analyte,
        sqlite_current = sqlite3.connect(r'C:\sqlite\IWR62.sqlite'),
        color_sqlite = sqlite3.connect(r'C:\sqlite\Lake_Color_Classification_IWR_62.sqlite'),
        derivationData = pd.read_csv(r'C:\development_2\NNC_data.csv')):
        super().__init__(wbid, start_yr, analyte)
        # self.NNC = NNC
        self.sqlite = sqlite_current
        self.color_sqlite = color_sqlite
        self.derivationData = derivationData

    def sqliteDestination(self, folder):
        self.sqlite  = sqlite3.connect(folder)
        return self.sqlite

    def dataExtraction(self):
        SQLquery = '''SELECT * FROM RawData WHERE wbid in ('%s')
        AND mastercode in (%s)
        AND year >= (%s)''' %(self.wbid, self.analyte, self.start_yr) 
        nutrients_df = pd.read_sql_query(SQLquery, self.sqlite)
        return nutrients_df


# This is more the interfacing side
class dataPull:
    def __init__(self, wbid, start_yr, analyte):
        self.nutrients =  sourceData(wbid, start_yr, analyte)

    def iwrRUN(self, folder): #r'C:\sqlite\IWR62.sqlite'
        self.nutrients.sqliteDestination(str(folder))

    def rawData(self):
        return self.nutrients.dataExtraction()

    def NNC_derivation(self):
        return self.nutrients.derivationData
    
    def NNC_criteria(self):
        NNC = {'Type': [1, 2, 3], 'Color_&_Alk': ['> 40 Platinum Colbalt Units',
                           '≤ 40 Platinum Cobalt Units and > 20 mg/L CaCO3',
                           '≤ 40 Platinum Cobalt Units and ≤ 20 mg/L CaCO3' ],
                           'Min_TP_NNC_(mg/L)': [0.05, 0.03, 0.01],
                           'Min_TN_NNC_(mg/L)': [1.27, 1.05, 0.51]}
        NNC = pd.DataFrame.from_dict(NNC).set_index('Type')
        return NNC

    def wbid(self):
        return self.nutrients.wbid
    
    def wbidCheck(self):
        wbid_check = "SELECT * FROM RawData WHERE wbid in ('%s')" % (self.nutrients.wbid)
        wbid_check = pd.read_sql_query(wbid_check, self.nutrients.sqlite)
        if len(wbid_check) == 0:
            error_string = "WBID " + "'" + self.nutrients.wbid + "' " + "does not exist or input is not formatted correctly!"
            print(error_string)

    def colorClass(self):
        # Performing Color Classification
        color_class = "SELECT * FROM Lake_CLassification WHERE wbid in ('%s')" % (self.nutrients.wbid)
        color_check = pd.read_sql_query(color_class, self.nutrients.color_sqlite)
        
        color_check.columns.values[[0, 1]] = ['WBID', 'COLOR']
        color_check = color_check.reset_index()
        color = color_check.loc[0, "COLOR"]
        
        if color == 1:
            clr_type = 'color'
            print(self.nutrients.wbid + ' is a high color lake')
        else:
            clr_type = 'clear'
            print(self.nutrients.wbid + ' is a low color lake')
        return clr_type, color
        
    def qaFiltered(self):
        nutrients_df = self.nutrients.dataExtraction()
        nutrients_df = nutrients_df[nutrients_df.STA.str.contains("21FLKWAT") == False]
        nutrients_df = nutrients_df[(nutrients_df['result'] > 0)]
        # Filter qualifier codes
        nutrients_df["mdl"] = pd.to_numeric(nutrients_df["mdl"])
        square_2 = sqrt(2)
        expression = nutrients_df["mdl"]/square_2
        nutrients_df["result"] = np.where((nutrients_df["rcode"] == "U") | (nutrients_df["rcode"] == "T"), expression, nutrients_df["result"])
        nutrients_df = nutrients_df.drop(nutrients_df[(nutrients_df["rcode"] == "G") | (nutrients_df["rcode"] == "V")].index)
        # Creating unique ID to calculate daily average of results with same date, station ID, and mastercode
        nutrients_df['date'] = pd.to_datetime(nutrients_df[['year','month', 'day']])
        nutrients_df['date'] = nutrients_df['date'].dt.strftime('%Y-%m-%d')
        nutrients_df['med_date'] = nutrients_df[['date', 'mastercode']].apply(lambda x: ''.join(x), axis=1)
        avg_samples = nutrients_df.groupby('med_date', as_index=False).agg({"result": "median"})
        # Creating dictionary of avg samples by station and date
        avg_dict = avg_samples.set_index('med_date').to_dict()['result']
        # Dropping duplicate Station Dates
        nutrients_df = nutrients_df.drop_duplicates(subset=['med_date'])
        # Replacinnutrients_dfg main dataframe with averages
        nutrients_df['result'] = nutrients_df['med_date'].map(avg_dict)
        # Filter results for calculating geomeans - must be >= 4 samples per year and at least 1 sample in wet season and at least 1 sample in dry
        nutrients_df['result'] = nutrients_df.groupby(["year", "mastercode"])['result'].transform(lambda x: x if len(x) >= 4 else np.nan)
        nutrients_df = nutrients_df.sort_values(["year"])
        nutrients_df['Season'] = 'N'
        nutrients_df.loc[(nutrients_df['month'].between(4,10, inclusive = False)), 'Season'] = 'G'
        nutrients_df['Count_G'] = nutrients_df.groupby(['year', 'mastercode'])['Season'].transform(lambda x: x[x.str.contains('G')].count())
        nutrients_df['Count_N'] = nutrients_df.groupby(['year', 'mastercode'])['Season'].transform(lambda x: x[x.str.contains('N')].count())
        mask = ((nutrients_df['Count_G'] <= 0) | (nutrients_df['Count_N'] <= 0))
        nutrients_df.loc[mask, ['result']] = np.nan
        # Drop NaN values so that data is not lost to pivot table
        nutrients_df = nutrients_df.dropna(subset=['result'])
        # Calculate geometric means
        nutrients_df = pd.pivot_table(nutrients_df, values = 'result', index=['wbid','year'], columns = 'mastercode',aggfunc={"result":[gmean]}).reset_index()
        nutrients_df.columns = nutrients_df.columns.droplevel()
        nutrients_df.columns.values[[0, 1]] = ['WBID', 'YEAR']
        return nutrients_df



class frontendPlot:

    def __init__(self, wbid, NNC_derivation,
                 Title_dict = {'TN': 'Total Nitrogen', 'TP': 'Total Phosphorus', 'CHLAC': 'Chlorophyll-a'},
                 Label_dict = {'TN': 'Total Nitrogen (mg/L)', 'TP': 'Total Phosphorus (mg/L)', 'CHLAC': 'Chlorophyll-a (μg/L)'}):
        self.w = wbid
        self.NNC_derivation = NNC_derivation
        self.Title_dict = Title_dict
        self.Label_dict = Label_dict

    def outputLocation(self, folder_loc):
        dir = folder_loc + '\html_files'
        if not os.path.exists(dir):
            os.makedirs(dir)
        return output_file(folder_loc + "\\html_files\\" + str(self.w) + "_NNC_Derivation_Plot.html", title= "WBID " + str(self.w))

    def NonH1Plot(self, w, df, clr_type, xVar):
        plot_list = []

        for p in xVar:
            df = df.reset_index(drop=True)
            df['YEAR'] = pd.to_datetime(df['YEAR'], format= '%Y')
            CDS1 = df

            fig = figure(x_axis_type = "log", y_axis_type= "log", plot_width=1200, plot_height=600,
                                  title = 'WBID ' + str(self.w) + ' ' + str(self.Title_dict.get(str(p))) + ' vs ' + str(self.Title_dict.get("CHLAC")))
            scatt = fig.scatter(str(p), "CHLAC", source = CDS1, fill_alpha=0.6, fill_color= 'red', size = 8)
            fig.add_tools(HoverTool(renderers=[scatt], tooltips=[(str(self.w), '@'+ str(p))]))

            fig.x(self.NNC_derivation[str(p) + '_' + str(clr_type)], self.NNC_derivation['CHLA_' + str(clr_type)], fill_alpha= 0.6, line_color='grey', size = 8,
                                    legend_label= 'NNC Derivation ' + str(clr_type) + ' Data')

            fig.line(self.NNC_derivation[str(p) + '_AGMs_' + str(clr_type)], self.NNC_derivation[str(p) + '_Upper_' + str(clr_type)], line_dash = 'dashed')
            fig.line(self.NNC_derivation[str(p) + '_AGMs_' + str(clr_type)], self.NNC_derivation[str(p) + '_Predicted_' + str(clr_type)], line_dash = 'solid', line_color= 'black')
            fig.line(self.NNC_derivation[str(p) + '_AGMs_' + str(clr_type)], self.NNC_derivation[str(p) + '_Lower_' + str(clr_type)],line_dash = 'dashed')

            fig.title.align = 'center'
            fig.title.text_font_size = '16pt'
            fig.yaxis.axis_label = str(self.Label_dict.get("CHLAC"))
            fig.yaxis.axis_label_text_font_size = "12pt"
            fig.yaxis.major_label_text_font_size = "12pt"
            fig.xaxis.axis_label = str(self.Label_dict.get(str(p)))
            fig.xaxis.axis_label_text_font_size = "12pt"
            fig.xaxis.major_label_text_font_size = "12pt"
            fig.axis.axis_label_text_font_style = 'bold'

            # legend alteration
            fig.legend.location = 'top_left'
            fig.legend.click_policy = 'hide'

            plot_list.append(fig)
        plots = column(*plot_list)
        return plots

    def savePlot(self, plots):
        save(plots)









