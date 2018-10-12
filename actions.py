from rasa_core_sdk import Action
from rasa_core_sdk.events import SlotSet, BotUttered

class ActionAskCraScanCallBackNum(Action):
   def name(self):
      # type: () -> Text
      return "action_cra_call_back_number"

   def run(self, dispatcher, tracker, domain):
      # type: (Dispatcher, DialogueStateTracker, Domain) -> Text

      #cuisine = tracker.get_slot('cuisine')
      #q = "select * from restaurants where cuisine='{0}' limit 1".format(cuisine)
      #result = db.query(q)
      print(dispatcher)
      print(tracker)
      print(domain)
      return [BotUttered(text="Action: What is the call back number that the CRA agent gave you?")]
