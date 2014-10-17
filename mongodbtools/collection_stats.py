#!/usr/bin/env python

"""
This script prints some basic collection stats about the size of the
collections and their indexes.
"""

from prettytable import PrettyTable
import psutil
from pymongo import Connection
from pymongo import ReadPreference
from optparse import OptionParser
import functools

TABLE_COLS = ["Collection", "Count", "% Size", "DB Size", "Avg Obj Size", "Indexes", "Index Size"]

def compute_signature(index):
    signature = index["ns"]
    for key in index["key"]:
        signature += "%s_%s" % (key, index["key"][key])
    return signature

def get_collection_stats(database, collection):
    print "Checking DB: %s" % collection.full_name
    return database.command("collstats", collection.name)

def get_cli_options():
    parser = OptionParser(usage="usage: python %prog [options]",
                          description="""This script prints some basic collection stats about the size of the collections and their indexes.""")

    parser.add_option("-H", "--host",
                      dest="host",
                      default="localhost",
                      metavar="HOST",
                      help="MongoDB host")
    parser.add_option("-p", "--port",
                      dest="port",
                      default=27017,
                      metavar="PORT",
                      help="MongoDB port")
    parser.add_option("-d", "--database",
                      dest="database",
                      default="",
                      metavar="DATABASE",
                      help="Target database to generate statistics. All if omitted.")
    parser.add_option("-u", "--user",
                      dest="user",
                      default="",
                      metavar="USER",
                      help="Admin username if authentication is enabled")
    parser.add_option("--password",
                      dest="password",
                      default="",
                      metavar="PASSWORD",
                      help="Admin password if authentication is enabled")
    parser.add_option("-s",
                      dest="sortby",
                      default="Collection",
                      choices=TABLE_COLS,
                      metavar="COLLECTION",
                      help="Key to sort table by")
    parser.add_option("-r",
                      dest="reversesort",
                      default=False,
                      action="store_true",
                      help="Sort descending")

    (options, args) = parser.parse_args()

    return options

def get_connection(host, port, username, password):
    userPass = ""
    if username and password:
        userPass = username + ":" + password + "@"

    mongoURI = "mongodb://" + userPass + host + ":" + str(port)
    return Connection(host=mongoURI, read_preference=ReadPreference.SECONDARY)

# From http://www.5dollarwhitebox.org/drupal/node/84
def convert_bytes(bytes):
    bytes = float(bytes)
    magnitude = abs(bytes)
    if magnitude >= 1099511627776:
        terabytes = bytes / 1099511627776
        size = '%.2fT' % terabytes
    elif magnitude >= 1073741824:
        gigabytes = bytes / 1073741824
        size = '%.2fG' % gigabytes
    elif magnitude >= 1048576:
        megabytes = bytes / 1048576
        size = '%.2fM' % megabytes
    elif magnitude >= 1024:
        kilobytes = bytes / 1024
        size = '%.2fK' % kilobytes
    else:
        size = '%.2fb' % bytes
    return size

def unconvert_bytes(bytestring):
    suffix = bytestring[-1]
    num = float(bytestring[:-1])
    if suffix == 'T':
        return num * 1099511627776
    elif suffix == 'G':
        return num * 1073741824
    elif suffix == 'M':
        return num * 1048576
    elif suffix == 'K':
        return num * 1024
    else:
        return num

def format_row_for_sort(row):
    if type(row[0]) == int:
        return row
    elif row[0][-1] == '%':
        row[0] == float(row[0][:-1])
    elif row[0][-1] in ('b', 'K', 'M', 'G', 'T') \
        and row[0][-2].isdigit():
        # hilarious heuristic for detecting this
        row[0] = unconvert_bytes(row[0]) 
    return row

def main(options):
    summary_stats = {
        "count" : 0,
        "size" : 0,
        "indexSize" : 0
    }
    all_stats = []

    connection = get_connection(options.host, options.port, options.user, options.password)

    all_db_stats = {}

    databases= []
    if options.database:
        databases.append(options.database)
    else:
        databases = connection.database_names()

    for db in databases:
        # FIXME: Add an option to include oplog stats.
        if db == "local":
            continue

        database = connection[db]
        all_db_stats[database.name] = []
        for collection_name in database.collection_names():
            stats = get_collection_stats(database, database[collection_name])
            all_stats.append(stats)
            all_db_stats[database.name].append(stats)

            summary_stats["count"] += stats["count"]
            summary_stats["size"] += stats["size"]
            summary_stats["indexSize"] += stats.get("totalIndexSize", 0)

    x = PrettyTable(TABLE_COLS)
    x.align["Collection"]  = "l"
    x.align["% Size"]  = "r"
    x.align["Count"]  = "r"
    x.align["DB Size"]  = "r"
    x.align["Avg Obj Size"]  = "r"
    x.align["Index Size"]  = "r"
    x.padding_width = 1

    print

    for db in all_db_stats:
        db_stats = all_db_stats[db]
        count = 0
        for stat in db_stats:
            count += stat["count"]
            x.add_row([stat["ns"], stat["count"], "%0.1f%%" % ((stat["size"] / float(summary_stats["size"])) * 100),
                       convert_bytes(stat["size"]),
                       convert_bytes(stat.get("avgObjSize", 0)),
                       stat.get("nindexes", 0),
                       convert_bytes(stat.get("totalIndexSize", 0))])

    print

    # pretty table is a pretty shit library, doesnt have separate formatting for
    # different columns, and the sortby simply rearranges the order of columns
    # in a row which makes it impossible to apply an intelligent sort_key, which
    # really should be named 'pre_search_formatter'
    print x.get_string(
        sortby=options.sortby,
        sort_key=format_row_for_sort,
        reversesort=options.reversesort)

    print "Total Documents:", summary_stats["count"]
    print "Total Data Size:", convert_bytes(summary_stats["size"])
    print "Total Index Size:", convert_bytes(summary_stats["indexSize"])

    # this is only meaningful if we're running the script on localhost
    if options.host == "localhost":
        ram_headroom = psutil.phymem_usage()[0] - summary_stats["indexSize"]
        print "RAM Headroom:", convert_bytes(ram_headroom)
        print "RAM Used: %s (%s%%)" % (convert_bytes(psutil.phymem_usage()[1]), psutil.phymem_usage()[3])
        print "Available RAM Headroom:", convert_bytes((100 - psutil.phymem_usage()[3]) / 100 * ram_headroom)

if __name__ == "__main__":
    options = get_cli_options()
    main(options)
