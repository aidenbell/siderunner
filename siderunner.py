"""

    Program.....: sidetest.py
    Author......: Herb Lainchbury
    License.....: (C) 2012 Dynamic Solutions Inc.
    Description.: SeleniumIDE test runner for Python
    
    Runs tests built in Selenium IDE using WebDriver in place without the need
    to export those tests.

    TODO:
      * subclass tests from unittest.TestCase?

"""


import os
import unittest
import xml.dom.minidom
import logging

logger = logging.getLogger()

from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

__all__ = ['SeleniumTestCase', 'SeleniumTestSuite']

target_cache = {}


def totext(node):
    if hasattr(node,'data'):
        return node.data
    elif node.toxml() == '<br/>':
        return '\n'
    else:
        return ''


def getCommand(nodelist):
    rc = []
    for node in nodelist:
        if node.childNodes == []:
            rc.append(None)
        else:
            rc.append(''.join(totext(n) for n in node.childNodes))
    return rc


def find_element(driver, target):

    if target in target_cache:
        target = target_cache[target]

    if target.startswith('link='):
        try:
            return driver.find_element_by_link_text(target[5:])
        except NoSuchElementException:
            # try lowercase version of link, work around text-transform bug
            result = driver.find_element_by_link_text(target[5:].lower())
            target_cache[target] = 'link=' + target[5:].lower()
            logger.info('   label %s is being cached as %s' % (target, target_cache[target]))
            return result

    elif target.startswith('//'):
        return driver.find_element_by_xpath(target)

    elif target.startswith('xpath='):
        return driver.find_element_by_xpath(target[6:])

    elif target.startswith('css='):
        return driver.find_element_by_css_selector(target[4:])

    elif target.startswith('id='):
        return driver.find_element_by_id(target[3:])

    elif target.startswith('name='):
        return driver.find_element_by_name(target[5:])

    else:
        direct = driver.find_element_by_name(target) or driver.find_element_by_id(target)
        if direct:
            return direct
        raise Exception('Don\'t know how to find %s' % target)


class SeleniumTestCase:

    def __init__(self, filename, suite, callback=None):
        self.filename = filename
        self.callback = callback
        self.suite = suite

        document = open(filename).read()

        try:
            dom = xml.dom.minidom.parseString(document)
        except Exception, e:
            raise Exception("Unable to parse Selenium XML %s: %s"%(filename, e.message))

        self.commands = []

        rows = dom.getElementsByTagName('tr')
        for row in rows[1:]:
            self.commands.append( getCommand(row.getElementsByTagName('td')) )

        for command in self.commands:
            if not hasattr(self, str(command[0])):
                raise Exception('Unknown Selenium IDE command %s' % command)

    def _wait_for_body(self, driver, timeout=10):
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    def run(self, driver, url):

        self.base_url = url

        logger.info('running '+self.filename)

        for command in self.commands:
            method = getattr(self, str(command[0]))
            args = []
            if command[1] != None:
                args.append(command[1])
            if command[2] != None:
                args.append(command[2])
            logger.info('   ' + ' '.join([command[0]]+[repr(a) for a in args]).splitlines()[0])

            # Replace any arguments that contain stored values
            for argi, arg in enumerate(args):
                if not arg.startswith('${'):
                    continue
                varname = arg.strip()[2:-1]
                val = self.suite.get_stored_value(driver, varname)
                args[argi] = val

            try:
                method(driver, *args)
            except Exception, e:
                print "Error in %s: %s"%(self.filename, command), e.message
                raise e


            if self.callback:
                self.callback(driver.page_source)

    def open(self, driver, url):
        driver.get(self.base_url + url)

    def click(self, driver, target):
        find_element(driver, target).click()

    def clickAndWait(self, driver, target, value=None):
        elem = find_element(driver, target)

        if value != None:
            assert elem.text == value

        elem.click()
        self._wait_for_body(driver)

    def assertTitle(self, driver, text):
        sa,sb = (driver.title.strip(), text.strip())
        if sa != sb:
            raise Exception("Assert page title \"%s\"!=\"%s\""%(sa, sb))

    def storeText(self, driver, elem, name):
        self.suite.set_stored_value(driver,name, find_element(driver, elem).text)

    def waitForTitle(self, driver, value=''):
        try:
            # Waiting for the title isn't simple, so we wait for the <body>
            # tag by which time the driver should have a title value
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        finally:
            assert driver.title == value

    def waitForVisible(self, driver, selector):
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located(find_element(driver, selector)))
        finally:
            return

    def type(self, driver, target, text=''):
        element = find_element(driver, target)
        element.click()
        element.clear()
        element.send_keys(text)
    
    def select(self, driver, target, value):
        element = find_element(driver, target)
        if value.startswith('label='):
            Select(element).select_by_visible_text(value[6:])
        else:
            raise Exception("Don\'t know how to select %s on %s" % (value, target))

    def verifyTextPresent(self, driver, text):
        try:
            source = driver.page_source
            assert bool(text in source)
        except:
            print 'verifyTextPresent: ',repr(text),'not present in',repr(source)
            raise

    def verifyTextNotPresent(self, driver, text):
        try:
            assert not bool(text in driver.page_source)
        except:
            print 'verifyNotTextPresent: ',repr(text),'present'
            raise

    def assertElementPresent(self, driver, target):
        try:
            assert bool(find_element(driver, target))
        except:
            print 'assertElementPresent: ', repr(target), 'not present'
            raise

    def verifyElementPresent(self, driver, target):
        try:
            assert bool(find_element(driver, target))
        except:
            print 'verifyElementPresent: ', repr(target), 'not present'
            raise

    def verifyElementNotPresent(self, driver, target):
        present = True
        try:
            find_element(driver, target)
        except NoSuchElementException:
            present = False

        try:
            assert not present
        except:
            print 'verifyElementNotPresent: ', repr(target), 'present'
            raise

    def waitForTextPresent(self, driver, text):
        try:
            assert bool(text in driver.page_source)
        except:
            print 'waitForTextPresent: ',repr(text),'not present'
            raise

    def waitForTextNotPresent(self, driver, text):
        try:
            assert not bool(text in driver.page_source)
        except:
            print 'waitForTextNotPresent: ',repr(text),'present'
            raise

    def assertText(self, driver, target, value=u''):
        try:
            target_value = find_element(driver, target).text
            logger.info('  assertText target value ='+repr(target_value))
            if value.startswith('exact:'):
                assert target_value == value[len('exact:'):]
            else:
                assert target_value == value
        except:
            print 'assertText: ', repr(target), repr(find_element(driver, target).get_attribute('value')), repr(value)
            raise

    def assertValue(self, driver, target, value=u''):
        try:
            target_value = find_element(driver, target).get_attribute('value')
            logger.info('  assertNotValue target value ='+repr(target_value))
            assert target_value == value
        except:
            print 'assertValue: ', repr(target), repr(find_element(driver, target).get_attribute('value')), repr(value)
            raise

    def assertNotValue(self, driver, target, value=u''):
        try:
            target_value = find_element(driver, target).get_attribute('value')
            logger.info('  assertNotValue target value ='+repr(target_value))
            assert target_value != value
        except:
            print 'assertNotValue: ', repr(target), repr(target_value), repr(value)
            raise

    def selectWindow(self, driver, window):
        pass


class SeleniumTestSuite:

    def __init__(self, filename, callback=None):
        path = os.path.split(filename)[0]
        self.callback = callback
        # This is to support storeText commands
        self.stored_text = {}

        document = open(filename).read()
        dom = xml.dom.minidom.parseString(document)

        self.tests = []

        rows = dom.getElementsByTagName('tr')
        self.title = rows[0].getElementsByTagName('b')[0].childNodes[0].data
        for row in rows[1:]:

            title = row.getElementsByTagName('a')[0].childNodes[0].data
            test_filename = row.getElementsByTagName('a')[0].attributes.items()[0][1]
            self.tests.append((title, SeleniumTestCase(os.path.join(path, test_filename), self, self.callback)))

    def run(self, driver, url):
        for title, test in self.tests:
            try:
                test.run(driver, url)
            except:
                print 'Error in %s (%s)' % (title, test.filename)
                raise

    def get_stored_value(self, driver, name):
        return self.stored_text[name]

    def set_stored_value(self, driver, name, value):
        self.stored_text[name] = value

    def __repr__(self):
        tests = '\n'.join(['%s - %s' % (title,test.filename) for title,test in self.tests])
        return '%s\n%s' % (self.title, tests)


