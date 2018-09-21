from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import json
from flask import Blueprint, jsonify, request, Response
from flask_cors import CORS
from multiprocessing import Queue
from threading import Thread
from collections import defaultdict
from datetime import datetime
import logging
from uuid import uuid4

from rasa_core import utils
from rasa_nlu.server import check_cors
from rasa_core.channels.channel import UserMessage
from rasa_core.channels.channel import InputChannel, OutputChannel, QueueOutputChannel, CollectingOutputChannel
from rasa_core.events import SlotSet

logger = logging.getLogger()


class FileMessageStore:

    DEFAULT_FILENAME = "message_store.json"

    def __init__(self, filename=DEFAULT_FILENAME):
        self._store = defaultdict(list)
        self._filename = filename
        try:
            for k, v in json.load(open(self._filename, "r")).items():
                self._store[k] = v
        except IOError:
            pass

    def log(self, cid, username, message, uuid=None):
        if uuid is None:
            uuid = str(uuid4())
        self._store[cid].append(
            {
                "time": datetime.utcnow().isoformat(),
                "username": username,
                "message": message,
                "uuid": uuid,
            }
        )
        self.save()

    def clear(self, cid):
        self._store[cid] = []
        self.save()

    def save(self):
        json.dump(self._store, open(self._filename, "w"))

    def __getitem__(self, key):
        return self._store[key]


class BotServerOutputChannel(OutputChannel):
    def __init__(self, message_store):
        self.message_store = message_store

    def send_text_message(self, recipient_id, message):
        self.message_store.log(recipient_id, "bot", {"type": "text", "text": message})

    def send_text_with_buttons(self, recipient_id, message, buttons, **kwargs):
        # type: (Text, Text, List[Dict[Text, Any]], **Any) -> None
        """Sends buttons to the output.
        Default implementation will just post the buttons as a string."""

        self.send_text_message(recipient_id, message)
        self.message_store.log(
            recipient_id, "bot", {"type": "button", "buttons": buttons}
        )

    def send_image_url(self, recipient_id, image_url):
        # type: (Text, Text) -> None
        """Sends an image. Default will just post the url as a string."""

        self.message_store.log(
            recipient_id, "bot", {"type": "image", "image": image_url}
        )


class BotServerInputChannel(InputChannel):
    
    def __init__(
        self, agent, message_store=FileMessageStore()
    ):
        logging.basicConfig(level="DEBUG")
        logging.captureWarnings(True)
        self.message_store = message_store
        self.on_message = lambda x: None
        self.cors_origins = [u'*']
        self.agent = agent

    @classmethod
    def name(cls):
        return "bot"

    @staticmethod
    def on_message_wrapper(on_new_message, text, queue, sender_id):
        collector = QueueOutputChannel(queue)

        message = UserMessage(text, collector, sender_id)
        on_new_message(message)

        queue.put("DONE")

    def stream_response(self, on_new_message, text, sender_id):
        from multiprocessing import Queue

        q = Queue()

        t = Thread(target=self.on_message_wrapper,
                   args=(on_new_message, text, q, sender_id))
        t.start()
        while True:
            response = q.get()
            if response == "DONE":
                break
            else:
                yield json.dumps(response) + "\n"
    
    def blueprint(self, on_new_message):
        custom_webhook = Blueprint('custom_webhook', __name__)

        CORS(custom_webhook)

        @custom_webhook.route("/health", methods=['GET'])
        def health():
            return jsonify({"status": "ok"})

        @custom_webhook.route("/", methods=['GET'])
        def default():
            return jsonify({"component": "bot"})
        
        @custom_webhook.route("/conversations/<cid>/log", methods=['GET'])
        def show_log(cid):
            #request.setHeader("Content-Type", "application/json")
            print("--- Log")
            print(self.message_store[cid])
            print("---")
            return json.dumps(self.message_store[cid])

        @custom_webhook.route("/conversations/<cid>/say", methods=['GET'])
        def say(cid):
            #print("## request.args ->")
            #print(request.args)
            message = request.args["message"]
            #_payload = request.args["payload"]
            #_display_name = request.args["display_name"]
            _uuid = request.args["uuid"]
            logger.info(message)

            tracker = self.agent.tracker_store.get_or_create_tracker(cid)

            if message == "_restart":
                self.message_store.clear(cid)
            else:
                if len(_uuid) > 0:
                    self.message_store.log(
                        cid,
                        cid,
                        {"type": "text", "text": message},
                        _uuid,
                    )
                else:
                    self.message_store.log(
                        cid, cid, {"type": "text", "text": message}
                    )

                should_use_stream = utils.bool_arg("stream", default=False)

                if should_use_stream:
                    return Response(
                        self.stream_response(on_new_message, message, cid),
                        content_type='text/event-stream')
                else:
                    collector = CollectingOutputChannel()
                    on_new_message(UserMessage(message, collector, cid))
                    #print("$$$ Bot response")
                    #print(collector.messages)
                    for msg in collector.messages:
                        recipient_id = msg['recipient_id']
                        res_message = msg['text']
                        self.message_store.log(cid, "bot", {"type": "text", "text": res_message}, recipient_id)
                    # the return here is for sync fetch testing
                    return jsonify(collector.messages)

        return custom_webhook



