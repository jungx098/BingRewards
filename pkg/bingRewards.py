#!/usr/bin/env python2

#
# developed by Sergey Markelov (2013)
#

from __future__ import with_statement

import cookielib
import random
import time
import urllib
import urllib2
import ssl
import importlib
import re

import bingCommon
import bingDashboardParser as bdp
import bingHistory
import helpers

# extend urllib.addinfourl like it defines @contextmanager (to use with "with" keyword)
urllib.addinfourl.__enter__ = lambda self: self
urllib.addinfourl.__exit__  = lambda self, type, value, traceback: self.close()

class HTTPRefererHandler(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        if not "Referer" in req.headers:
#             if req.get_host() == "www.bing.com":
#                 req.headers["Referer"] = "http://www.bing.com/"
#             else:
                req.headers["Referer"] = req.get_full_url()
        return urllib2.HTTPRedirectHandler.http_error_302(self, req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_302

class BingRewards:
    class RewardResult:
        def __init__(self, reward):
            if reward is None or not isinstance(reward, bdp.Reward):
                raise TypeError("reward is not of Reward type")

            self.o = reward
            self.isError = False
            self.message = ""
            # action applied to the reward
            self.action  = bdp.Reward.Type.Action.WARN

    def __init__(self, httpHeaders, userAgents, config):
        """
        From _config_ these parameters are used:
            config.general.betweenQueriesInterval - (double) - how many seconds the script should wait between queries
            config.general.betweenQueriesSalt     - (double) - up to how many seconds to wait on top of _betweenQueriesInterval_ (rand(0, salt))
            config.proxy - proxy settings (can be None)
        """

        self.betweenQueriesInterval = float(config.general.betweenQueriesInterval)
        self.betweenQueriesSalt     = float(config.general.betweenQueriesSalt)
        self.addSearchesDesktop     = int(config.general.addSearchesDesktop)
        self.addSearchesDesktopSalt = int(config.general.addSearchesDesktopSalt)
        self.addSearchesMobile      = int(config.general.addSearchesMobile)
        self.addSearchesMobileSalt  = int(config.general.addSearchesMobileSalt)
        self.openTopLinkRange       = int(config.general.openTopLinkRange)
        self.openLinkChance         = float(config.general.openLinkChance)
        self.ignoreSSLErrors        = int(config.general.ignoreSSLErrors)
        self.httpHeaders = httpHeaders
        self.userAgents  = userAgents
        self.queryGenerator = config.queryGenerator

        self.cookies = cookielib.CookieJar()
        
        # if ignoreSSLErrors == True, create SSL Context to ignore SSL errors 
        ctx = None
        if self.ignoreSSLErrors:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        if config.proxy:
            if config.proxy.login:
                proxyString = "%s:%s@%s" % ( config.proxy.login, config.proxy.password, config.proxy.url )
            else:
                proxyString = config.proxy.url

            print "Protocols: '%s', Proxy: '%s'" % ( ", ".join(config.proxy.protocols), proxyString )

            self.opener = urllib2.build_opener(
                                            urllib2.ProxyHandler( { p : proxyString for p in config.proxy.protocols } ),
                                            #urllib2.HTTPSHandler(debuglevel = 1),     # be verbose on HTTPS
                                            #urllib2.HTTPHandler(debuglevel = 1),      # be verbose on HTTP
                                            urllib2.HTTPSHandler(context=ctx),
                                            HTTPRefererHandler,                       # add Referer header on redirect
                                            urllib2.HTTPCookieProcessor(self.cookies))     # keep cookies

        else:
            self.opener = urllib2.build_opener(
                                            #urllib2.HTTPSHandler(debuglevel = 1),     # be verbose on HTTPS
                                            #urllib2.HTTPHandler(debuglevel = 1),      # be verbose on HTTP
                                            urllib2.HTTPSHandler(context=ctx),
                                            HTTPRefererHandler,                       # add Referer header on redirect
                                            urllib2.HTTPCookieProcessor(self.cookies))     # keep cookies

    def getLifetimeCredits(self):
        page = self.getDashboardPage()
        # Figure out which version of the rewards page we're on
        if page.find("rewards-oneuidashboard") != -1:
            block = page.split("var dashboard")[1]
            return int(block[block.index('"lifetimePoints"'):].split(',')[0].split(':')[1])
        else:
            # find lifetime points
            s = page.find(' lifetime points</div>') - 20
            s = page.find('>', s) + 1
            e = page.find(' ', s)
            points = page[s:e]
            points = int(points.replace(",", "")) # remove commas so we can cast as int

            if True == points.isdigit(): return int(points)

        #should never happen...
        return 0

    def getDashboardPage(self):
        """
        Returns https://account.microsoft.com/rewards Lifetime Credits
        The number of credits earned since day one of the account
        """
        url = "https://account.microsoft.com/rewards/dashboard"
        request = urllib2.Request(url = url, headers = self.httpHeaders)
        request.add_header("Referer", bingCommon.BING_URL)
        with self.opener.open(request) as response:
            referer = response.geturl()
            page = helpers.getResponseBody(response)

        # If we have already gone through the sign in process once, we don't need to do it again, just return the page
        if page.find('JavaScript required to sign in') == -1:
            return page

        # get form data
        s = page.index('action="')
        s += len('action="')
        e = page.index('"', s)
        action = page[s:e]

        s = page.index("NAP")
        s = page.index('value="', s)
        s += len('value="')
        e = page.index('"', s)
        nap = page[s:e]

        s = page.index("ANON")
        s = page.index('value="', s)
        s += len('value="')
        e = page.index('"', s)
        anon = page[s:e]

        s = page.index('id="t"')
        s = page.index('value="', s)
        s += len('value="')
        e = page.index('"', s)
        t = page[s:e]

        s = page.index('id="pprid"')
        s = page.index('value="', s)
        s += len('value="')
        e = page.index('"', s)
        pprid = page[s:e] 

        postFields = urllib.urlencode({
            "NAP"    : nap,
            "ANON"   : anon,
            "t"      : t,
            "pprid"  : pprid
        })

        request = urllib2.Request(action, postFields, self.httpHeaders)
        request.add_header("Referer", referer)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)

        return page 

    def getRewardsPoints(self):
        """Returns rewards points as int"""
        # report activity
        postFields = urllib.urlencode( { "url" : bingCommon.BING_URL, "V" : "web" } )
        url = "http://www.bing.com/rewardsapp/reportActivity"
        request = urllib2.Request(url, postFields, self.httpHeaders)
        request.add_header("Referer", bingCommon.BING_URL)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)

        if len(page) == 0:
            raise Exception("Rewards points page is empty. That could mean you are not signed up for rewards with this account")

         # There are instances where the account appears to be signed in, but really is not
        helpers.errorOnText(page, "You are not signed in", "Temporary account ban: User was not successfully signed in.\n")

        # parse activity page
        indCheck = "var b='"
        s = page.find(indCheck)
        if s == -1:
            indCheck = "t.innerHTML='"
            s = page.find(indCheck)
        s += len(indCheck)
        e = page.index("'", s)
        rewardsText = page[s:e]
        if rewardsText == 'Rewards': # The account is banned
            raise helpers.BingAccountError("Banned from BingRewards: Could not get the number of rewards.")
        elif True != rewardsText.isdigit():
            print "Reward point parsing failure: " + rewardsText
            return 0
        else:
            return int(rewardsText)

    def __processHit(self, reward):
        """Processes bdp.Reward.Type.Action.HIT and returns self.RewardResult"""
        res = self.RewardResult(reward)
        if reward.isAchieved():
            res.message = "This reward has been already achieved"
            return res

        pointsEarned = self.getRewardsPoints()
        currPage = self.getDashboardPage()
        startIndex = currPage.find('__RequestVerificationToken')
        endIndex = currPage[startIndex:].find('/>')
        # pad here to get to the correct spot
        verificationAttr = currPage[startIndex+49:startIndex+endIndex-2]

        verificationData = [
            ('id', reward.hitId),
            ('hash', reward.hitHash),
            ('timeZone', '-300'),
            ('activityAmount', '1'),
            ('__RequestVerificationToken', verificationAttr) #there was a comma here, removed it. Monitor to make sure shit still works
        ]

        verificationUrl = 'https://account.microsoft.com/rewards/api/reportactivity?refd=www.bing.com&X-Requested-With=XMLHttpRequest'

        request = urllib2.Request(url = verificationUrl, headers = self.httpHeaders)
        with self.opener.open(request, urllib.urlencode(verificationData)) as response:
            page = helpers.getResponseBody(response)
        pointsEarned = self.getRewardsPoints() - pointsEarned
        # if HIT is against bdp.Reward.Type.RE_EARN_CREDITS - check if pointsEarned is the same to
        # pointsExpected
        indCol = bdp.Reward.Type.Col.INDEX
        if reward.tp[indCol] == bdp.Reward.Type.RE_EARN_CREDITS[indCol]:
            pointsExpected = reward.progressMax - reward.progressCurrent
            if pointsExpected != pointsEarned:
                filename = helpers.dumpErrorPage(page)
                res.isError = True
                res.message = "Expected to earn " + str(pointsExpected) + " points, but earned " + \
                              str(pointsEarned) + " points. Check " + filename + " for further information"
        return res

    def __processQuiz(self, reward):
        """Processes bdp.Reward.Type.Action.QUIZ and returns self.RewardResult"""
        res = self.RewardResult(reward)
        if reward.isAchieved():
            res.message = "This reward has been already achieved"
            return res

        pointsEarned = self.getRewardsPoints()
        currPage = self.getDashboardPage()
        startIndex = currPage.find('__RequestVerificationToken')
        endIndex = currPage[startIndex:].find('/>')
        #pad here to get to the correct spot
        verificationAttr = currPage[startIndex+49:startIndex+endIndex-2]

        #TODO: last parameter is ', "Timezone" : 240'. Is it needed?
        verificationData = '{"ActivitySubType" : "quiz", "ActivityType" : "notification", "OfferId" : "' + reward.hitId + '", "Channel" : "Bing.Com", "PartnerId" : "BingTrivia"}'

        verificationUrl = 'https://www.bing.com/msrewards/api/v1/ReportActivity'

        print
        print "Running activity: %s" % reward.name
        print

        request = urllib2.Request(url = verificationUrl, headers = self.httpHeaders)
        for i in range( reward.progressCurrent, reward.progressMax, 10 ):
            print "%s - %2d/%2d - Activity: %s" % (helpers.getLoggingTime(), i+10, reward.progressMax, reward.name)
            with self.opener.open(request, verificationData) as response:
                page = helpers.getResponseBody(response)
            #default pause between guesses
            t = self.betweenQueriesInterval + random.uniform(0, self.betweenQueriesSalt)
            time.sleep(t)


        pointsEarned = self.getRewardsPoints() - pointsEarned
        # if QUIZ is against bdp.Reward.Type.RE_EARN_CREDITS - check if pointsEarned is the same to
        # pointsExpected
        indCol = bdp.Reward.Type.Col.INDEX
        if reward.tp[indCol] == bdp.Reward.Type.RE_EARN_CREDITS[indCol]:
            pointsExpected = reward.progressMax - reward.progressCurrent
            if pointsExpected != pointsEarned:
                filename = helpers.dumpErrorPage(page)
                res.isError = True
                res.message = "Expected to earn " + str(pointsExpected) + " points, but earned " + \
                              str(pointsEarned) + " points. Check " + filename + " for further information"
        return res

    def __processWarn(self, reward):
        """Processes bdp.Reward.Type.Action.WARN and returns self.RewardResult"""
        res = self.RewardResult(reward)

        if reward.isAchieved():
            res.message = "This reward has been already achieved"
            return res

        pointsEarned = self.getRewardsPoints()
        request = urllib2.Request(url = reward.url, headers = self.httpHeaders)
        try:
            with self.opener.open(request) as response:
                page = helpers.getResponseBody(response)
        except:
            res.isError = True
            res.message = "__processWarn: Unable to open url: '" + reward.url + "'"
            return res

        pointsEarned = self.getRewardsPoints() - pointsEarned
        # check if we earned any points
        if pointsEarned < 1:
            res.isError = True
            res.message = "Didn't earn any points for click"
        return res

    def __processSearch(self, reward, verbose):
        """Processes bdp.Reward.Type.Action.SEARCH and returns self.RewardResult"""

        BING_QUERY_URL = 'http://www.bing.com/search?q='
        BING_QUERY_SUCCESSFULL_RESULT_MARKER_PC = '<div id="b_content">'
        BING_QUERY_SUCCESSFULL_RESULT_MARKER_MOBILE = '<div id="content">'
        IG_PING_LINK = "http://www.bing.com/fd/ls/GLinkPingPost.aspx"
        IG_NUMBER_PATTERN = re.compile(r'IG:"([^"]+)"')
        IG_SEARCHES_PATTERN = re.compile(r'<li\s[^>]*class="b_algo"[^>]*><(?:h2|div\s[^>]*class="b_algoheader")><a\s[^>]*href="(http[^"]+)"\s[^>]*h="ID=([^"]+)"')

        res = self.RewardResult(reward)
        if reward.isAchieved():
            # res.message = "This reward has been already achieved"
            # return res
            print "This reward has been already achieved"

        indCol = bdp.Reward.Type.Col.INDEX

        # get a set of queries from today's Bing history
        url = bingHistory.getBingHistoryTodayURL()
        request = urllib2.Request(url = url, headers = self.httpHeaders)
        with self.opener.open(request) as response:
            page = helpers.getResponseBody(response)
        history = bingHistory.parse(page)

        # find out how many searches need to be performed
        matchesMobile = False
        matches = bdp.Reward.Type.SEARCH_AND_EARN_DESCR_RE.search(reward.description)
        # Mobile description changed, so check that one too
        if (reward.isAchieved() is False) and (matches is None):
            matches = bdp.Reward.Type.SEARCH_AND_EARN_DESCR_RE_MOBILE.search(reward.description)
            matchesMobile = True

        if reward.isAchieved():
            print "Reward is achieved, but continue search"
            res.isError = True
            res.message = " (random search: reward is achieved)"

            # Init searchesCount
            searchesCount = random.randint(0, 5)
        elif matches is None:
            print "No RegEx matches found for this search and earn"
            matchesMobile = False
            res.isError   = True
            res.message   = " (random search: no RegEx matches found)"

            # Init searchesCount
            searchesCount = random.randint(1, 5)
        else:
            maxRewardsCount  = int(matches.group(1))
            rewardsCount     = int(matches.group(2))
            rewardCost       = 1 # Looks like it's now always X points per one search
            searchesCount    = maxRewardsCount * rewardCost / rewardsCount

        # adjust to the current progress
        # reward.progressCurrent is now returning current points, not current searches
        # so divide it by points per search (rewardsCount) to get correct search count needed
            searchesCount -= (reward.progressCurrent * rewardCost) / rewardsCount

        if matchesMobile == True:
            # new mobile search description gives total search count + points per search for edge/non-edge
            edgeValue = int(matches.group(1))
            nonEdgeValue = int(matches.group(2))
            searchesCount = int(matches.group(3))
            # apparently ios uses EdgiOS, so we only check the first 3 letters not the full word 'edge'
            if self.userAgents.mobile.lower().find("edg") != -1:
                # we are searching on edge so points go to 200
                searchesCount -= reward.progressCurrent / edgeValue
            else:
                # non-edge search so 100 is the max
                searchesCount -= reward.progressCurrent / nonEdgeValue

        headers = self.httpHeaders

        if reward.tp == bdp.Reward.Type.SEARCH_PC or reward.tp == bdp.Reward.Type.SEARCH_AND_EARN:
            headers["User-Agent"] = self.userAgents.pc
            searchesCount += self.addSearchesDesktop + random.randint(0, self.addSearchesDesktopSalt)
            print
            print "Running PC searches"
            if reward.isAchieved() == True or matches == None:
                print "- Random exhaustive search"
            print
        elif reward.tp == bdp.Reward.Type.SEARCH_MOBILE:
            headers["User-Agent"] = self.userAgents.mobile
            searchesCount += self.addSearchesMobile + random.randint(0, self.addSearchesMobileSalt)
            print
            print "Running mobile searches"
            if reward.isAchieved() == True or matches == None:
                print "- Random exhaustive search"
            print
        else:
            res.isError = True
            res.message = "Don't know how to process this search"
            return res

        if verbose:
            print("User-Agent: {0}".format(bingCommon.HEADERS["User-Agent"]))
            print

        # Import the query generator
        try:
            qg = importlib.import_module(self.queryGenerator, package=None)
            queryGenerator = qg.queryGenerator(self)
        except ImportError:
            raise TypeError("{0} is not a module".format(self.queryGenerator))

        # generate a set of queries to run
        queries = queryGenerator.generateQueries(searchesCount, history)

        if len(queries) < searchesCount:
            print "Warning: not enough queries to run were generated!"
            print "Requested:", searchesCount
            print "Generated:", len(queries)

        successfulQueries = 0
        i = 1
        totalQueries = len(queries)

        for query in queries:
            if i > 1:
                # sleep some time between queries (don't worry Bing ;) )
                t = self.betweenQueriesInterval + random.uniform(0, self.betweenQueriesSalt)
                time.sleep(t)

            url = BING_QUERY_URL + urllib.quote_plus(query.encode('utf-8'))

            print "%s - %2d/%2d - Search: %s" % (helpers.getLoggingTime(), i, totalQueries, query)

            request = urllib2.Request(url = url, headers = bingCommon.HEADERS)
            with self.opener.open(request) as response:
                page = helpers.getResponseBody(response)

            # check for the successful marker
            found = page.find(BING_QUERY_SUCCESSFULL_RESULT_MARKER_PC) != -1 \
                 or page.find(BING_QUERY_SUCCESSFULL_RESULT_MARKER_MOBILE) != -1

            if not found:
                filename = helpers.dumpErrorPage(page)
                print "Warning! Query:"
                print "\t" + query
                print "returned no results, check " + filename + " file for more information"

            else:
                successfulQueries += 1

                # randomly open a link
                if self.openLinkChance > random.random():
                    # get IG number
                    ig_number = IG_NUMBER_PATTERN.search(page)
                    if ig_number is not None:
                        ig_number = ig_number.group(1)
                        ig_searches = IG_SEARCHES_PATTERN.findall(page)
                        # make sure we have at least 1 search
                        if len(ig_searches) > 0:
                            # get a random link to open
                            ig_max_rand = min(self.openTopLinkRange, len(ig_searches) - 1)
                            ig_link_num = random.randint(0, ig_max_rand)
                            ig_search = ig_searches[ig_link_num]

                            ig_link = IG_PING_LINK + '?' + urllib.urlencode([
                                ('IG', ig_number), ('ID', ig_search[1]), ('url', ig_search[0])
                            ])

                            # sleep a reasonable amount of time before clicking the link
                            # use defaults to save space in config
                            t = random.uniform(0.75, 3.0)
                            time.sleep(t)

                            # send the ping POST beacon as if we followed the link
                            request = urllib2.Request(ig_link, "", bingCommon.HEADERS)
                            request.add_header("Referer", response.url)
                            request.add_header("Content-Type", "text/plain;charset=UTF-8")
                            self.opener.open(request)

                            if verbose:
                                print("Followed Link {}".format(ig_link_num + 1))
                        else:
                            filename = helpers.dumpErrorPage(page)
                            print "Warning! No searches were found on search results page"
                            print "Check {0} file for more information".format(filename)
                    else:
                        filename = helpers.dumpErrorPage(page)
                        print "Warning! Could not find search result IG number"
                        print "Check {0} file for more information".format(filename)

            i += 1

        if successfulQueries < searchesCount:
            res.message = str(successfulQueries) + " out of " + str(searchesCount) + " requests were successfully processed" + \
                          res.message
        else:
            res.message = "All " + str(successfulQueries) + " requests were successfully processed" + \
                          res.message

        # reset header to pc so pc pages return in getting life time points
        headers["User-Agent"] = self.userAgents.pc

        return res

    def process(self, rewards, verbose):
        """
        Runs an action for each of rewards as described in self.RewardType
        returns results list of self.RewardResult objects
        """

        # If rewards is not valid, set rewards to an empty list for the
        # subsequent process to continue without rewards.
        if rewards is None or not isinstance(rewards, list):
            print "rewards is not an instance of list"
            rewards = list()

        results = []
        searchCnt = 0

        for r in rewards:
            if r.tp is None:
                action = bdp.Reward.Type.Action.WARN
            else:
                action = r.tp[bdp.Reward.Type.Col.ACTION]

            if action == bdp.Reward.Type.Action.HIT:
                res = self.__processHit(r)
            elif action == bdp.Reward.Type.Action.QUIZ:
                res = self.__processQuiz(r)
            elif action == bdp.Reward.Type.Action.WARN:
                res = self.__processWarn(r)
            elif action == bdp.Reward.Type.Action.SEARCH:
                if r.isAchieved():
                    res = self.RewardResult(r)
                    res.message = "This reward has been already achieved"
                else:
                    res = self.__processSearch(r, verbose)
                    searchCnt = searchCnt + 1
            else:
                res = self.RewardResult(r)

            res.action = action
            results.append(res)

        if searchCnt != 0: return results

        # If no search is performed, do random search
        # Random PC searches
        if random.random() < 0.25:
            searchCnt = 0
            oldPt     = 0
            newPt     = self.getRewardsPoints()

            while oldPt != newPt and searchCnt < 10:
                searchCnt = searchCnt + 1
                oldPt     = newPt

                r          = bdp.Reward()
                r.tp       = bdp.Reward.Type.SEARCH_PC
                res        = self.__processSearch(r, verbose)
                res.action = bdp.Reward.Type.Action.SEARCH

                results.append(res)

                newPt = self.getRewardsPoints()

        # Random mobile searches
        if random.random() < 0.25:
            searchCnt = 0
            oldPt     = 0
            newPt     = self.getRewardsPoints()

            while oldPt != newPt and searchCnt < 10:
                searchCnt = searchCnt + 1
                oldPt     = newPt

                r          = bdp.Reward()
                r.tp       = bdp.Reward.Type.SEARCH_MOBILE
                res        = self.__processSearch(r, verbose)
                res.action = bdp.Reward.Type.Action.SEARCH

                results.append(res)

                newPt = self.getRewardsPoints()

        return results

    def __printReward(self, reward):
        """Prints a reward"""
        print "name        : %s" % reward.name
        if reward.url != "":
            print "url         : %s" % reward.url
        if reward.progressMax != 0:
            print "progressCur : %d" % reward.progressCurrent
            print "progressMax : %d" % reward.progressMax
            print "progress %%  : %0.2f%%" % reward.progressPercentage()
        if reward.isDone:
            print "is done     : true"
        print "description : %s" % reward.description
        print "hit identifier: %s" % reward.hitId
        print "hit hash: %s" % reward.hitHash

    def printRewards(self, rewards):
        """
        Prints out rewards list
        throws TypeError if rewards is None or not instance of list
        """
        if rewards is None or not isinstance(rewards, list):
            return None # Do not stop for the process to continue
            raise TypeError("rewards is not an instance of list")

        i = 0
        total = len(rewards)
        for r in rewards:
            i += 1
            print "Reward %d/%d:" % (i, total)
            print "-----------"
            self.__printReward(r)
            print

    def __printResult(self, result):
        """Prints a result"""
        self.__printReward(result.o)
        if result.isError:
            print "   Error    :   true"
        print "   Message  : " + result.message
        print "   Action   : " + bdp.Reward.Type.Action.toStr(result.action)


    def printResults(self, results, verbose):
        """
        Prints out results list
        if verbose - prints all results, otherwise prints errors only
        throws TypeError if results is None or not instance of list
        """
        if results is None or not isinstance(results, list):
            raise TypeError("results is not an instance of list")

        i = 0
        total = len(results)
        for r in results:
            if verbose or r.isError:
                i += 1
                print "Result %d/%d:" % (i, total)
                print "-----------"
                self.__printResult(r)
                print
