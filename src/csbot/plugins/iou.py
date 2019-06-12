from csbot.plugin import Plugin
from csbot.util import nick

class IOU(Plugin):
    '''
    Records what we owe to each other
    '''
    db_owage = Plugin.use('mongodb', collection='owage')

    def setup(self):
        '''
        In case for some reason, the db isn't initialised, makes sure that it is 
        (and because a mongodb doesn't exist if it doesn't have a document, makes sure there is one.)
        Should really only be called once, ever.
        '''
        super(IOU, self).setup()

        #Check if owage already exists.
        if self.db_owage.find_one('example'):
            self.initialised = True
            return
        
        #If owage doesn't exist yet, we want to make it.
        self.initialised = False
        self.blankuser = {'_id': 'example', 'owee_nick': 0}
        x = self.db_owage.insert(self.blankuser)
    
    def get_owage(self, nick, owee_name):
        all_owed = self.db_owage.find_one(nick)
        if all_owed and owee_name in all_owed:
                return all_owed[owee_name]/100
            return 0
        return 0 
    
    def update_owage(self, nick, owee_name, amount):
        all_owed = self.db_owage.find_one(nick)
        if all_owed:
            self.db_owage.delete_one(all_owed)
            if owee_name in all_owed:
                all_owed[owee_name] = int(all_owed[owee_name])
                all_owed[owee_name] += int(amount*100)
            else:
                all_owed[owee_name] = int(amount*100)
        else:
            all_owed = {"_id": nick, owee_name: int(amount*100)}
        
        self.db_owage.insert_one(all_owed)  
        return self.get_owage(nick, owee_name)  


    @Plugin.command('iou', help=('iou <nick>: returns what you owe to that person '
                                    '| iou <nick> <amount> adds the amount (in pounds) to what you alread owe that person'))
    def iou(self, e):
        nick_ = nick(e['user']).strip('<')
        nick_ = nick_.strip('>')
        request = e['data']
        request_words = request.split()
        res = None
        if request.strip() == '':
            e.reply('Could not parse - please refer to help iou')
            return

        if len(request_words) == 2:
            try:
                float(request_words[1])
            except ValueError:
                e.reply('Please use an actual number')
            if not (-2**48 < int(request_words[1]) < 2**48):    
                #MongoDB has an 64-bit limit, enforcing a somewhat smaller limit just in case.
                e.reply('please use a smaller integer.')
                return
            res = self.update_owage(nick_, request_words[0], float(request_words[1]))
        if len(request_words) == 1:
            res = self.get_owage(nick_, request_words[0])
        if len(request_words)==0:
            e.reply('getting to it')
        
        if res is None:
            e.reply('Could not parse - please refer to help IOU')
        else:
            e.reply('you owe {} £{:.02f}.'.format(request_words[0], res))
        return

    
    @Plugin.command('iamowed', help=('iamowed <nick> tells you what nick owes you'))
    def iamowed(self, e):
        nick_ = nick(e['user']).strip('<')
        nick_ = nick_.strip('>')
        request = e['data']
        if request.strip() == '':
            e.reply('Could not parse - please refer to help iamowed')
            return
        request_words = request.split()
        res = None
        if len(request_words) == 1:
            res = self.get_owage(str((request_words[0])), nick_)
            e.reply('{} owes you £{}'.format(request, res))
            return
        e.reply('could not parse - please refer to help iamowed')
        return
