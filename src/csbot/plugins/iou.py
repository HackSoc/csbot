from csbot.plugin import Plugin
from csbot.util import nick

class IOU(Plugin):
    '''
    Records what we owe to each other
    '''
    db_owage = Plugin.use('mongodb', collection='owage')

    def setup(self):
        super(IOU, self).setup()

        #check if owage already exists
        if self.db_owage.find_one("example"):
            self.initialised = True
            return
        
        #if owage doesn't exist yet, we want to make it
        self.initialised = False

        self.blankuser = {"_id": "example", "owee_nick": 0}

        x = self.db_owage.insert(self.blankuser)
    
    def get_owage(self, nick, owee_name):
        all_owed = self.db_owage.find_one(nick)
        if all_owed:
            if owee_name in all_owed:
                return all_owed[owee_name]/100
            return 0
        return 0 #this is what I keep recieving
    
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
        
        self.db_owage.insert_one(all_owed)  #inserts updated value into db
        return self.get_owage(nick, owee_name)  #returns the updated amount
    
    def get_all_nicks(self):
        cursor = self.db_owage.find()
        nicks = []
        for document in cursor:
            nicks += cursor["_id"] 
        return nicks



    @Plugin.command('IOU', help = ('IOU <nick>: returns what you owe to that person '
                                    '| IOU <nick> <amount> adds the amount (in pounds) to what you alread owe that person'))
    @Plugin.command('iou', help = ('equivalent to IOU'))
    def iou(self, e):
        nick_ = nick(e['user']).strip('<')
        nick_ = nick_.strip('>')
        request = e['data']
        request_words = request.split(" ")
        res = None
        if request.strip(" ") == "":
            e.reply('Could not parse - please refer to help iou')
            return

        if len(request_words) == 2:
            try:
                float(request_words[1])
            except ValueError:
                e.reply('Please use an actual number')
            if not (-2**48 < int(request_words[1]) < 2**48):
                e.reply('stop with the fuckoff big integers')
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


#forgetting this for now because I'm just hitting a brick wall
    @Plugin.command('IAmOwed', help = ('Iamowed <nick> tells you what nick owes you'))
    @Plugin.command('iamowed', help = ('Iamowed <nick> tells you what nick owes you'))
    #hey froman transitivity when
    def iamowed(self, e):
        nick_ = nick(e['user']).strip('<')
        nick_ = nick_.strip('>')
        request = e['data']
        if request.strip(" ") == "":
            e.reply('Could not parse - please refer to help IAmOwed')
            return
        request_words = request.split(" ")
        res = None
        if len(request_words) == 1:
            res = self.get_owage(str((request_words[0])), nick_)
            e.reply('{} owes you £{}'.format(request, res))
            return
        e.reply('could not parse - please refer to help IAmOwed')
        return
