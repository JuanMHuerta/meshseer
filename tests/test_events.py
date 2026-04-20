import asyncio

import pytest

from meshseer.events import EventBroker, EventSubscriptionOverflow, TooManySubscribers


def test_subscription_rejects_connections_over_capacity():
    async def scenario():
        broker = EventBroker(max_connections=1)
        broker.attach_loop(asyncio.get_running_loop())

        async with broker.subscription():
            with pytest.raises(TooManySubscribers):
                async with broker.subscription():
                    pass

    asyncio.run(scenario())


def test_subscription_marks_overflow_and_stops_future_fanout():
    async def scenario():
        broker = EventBroker(queue_size=1)
        broker.attach_loop(asyncio.get_running_loop())

        async with broker.subscription() as subscription:
            broker.publish({"seq": 1})
            broker.publish({"seq": 2})
            await asyncio.sleep(0)

            with pytest.raises(EventSubscriptionOverflow):
                await subscription.get()

            queued = await subscription.queue.get()
            assert queued["seq"] == 1

            broker.publish({"seq": 3})
            await asyncio.sleep(0)

            assert subscription.queue.empty()
            assert subscription.overflowed.is_set() is True

    asyncio.run(scenario())
