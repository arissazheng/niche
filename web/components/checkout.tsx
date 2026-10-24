"use client";

import { Elements, LinkAuthenticationElement, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CheckoutIntent, Listing } from "@/lib/types";

const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
const stripePromise = publishableKey ? loadStripe(publishableKey) : null;

const appearance = {
  theme: "flat" as const,
  variables: { colorPrimary: "#000000", colorBackground: "#ffffff", borderRadius: "0px", fontFamily: "Helvetica Neue, Arial, sans-serif" },
};

/** In-page checkout (Stripe Payment Element with Link) — no redirect or separate tab. */
export function Checkout({ searchId, listing }: { searchId: string; listing: Listing }) {
  const [intent, setIntent] = useState<CheckoutIntent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.checkoutIntent(searchId, listing.id).then(setIntent, (e: Error) => setError(e.message));
  }, [searchId, listing.id]);

  if (error) return <p className="text-sm">{error}</p>;
  if (!intent) return <p className="label">Preparing checkout…</p>;

  const total = `${(intent.amount / 100).toFixed(2)} ${intent.currency}`;
  if (intent.mode === "fixture" || !intent.client_secret || !stripePromise) {
    return (
      <div className="grid gap-2">
        <p className="text-display">{total}</p>
        <p className="text-sm">Checkout is in fixture mode: set STRIPE_SECRET_KEY on the API and NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY here.</p>
        <button disabled className="rule-t rule-b text-display py-2 text-muted">Buy with Link</button>
      </div>
    );
  }
  return (
    <Elements stripe={stripePromise} options={{ clientSecret: intent.client_secret, appearance }}>
      <PayForm total={total} />
    </Elements>
  );
}

function PayForm({ total }: { total: string }) {
  const stripe = useStripe();
  const elements = useElements();
  const [state, setState] = useState<"idle" | "paying" | "done">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function pay(e: React.FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;
    setState("paying");
    const { error, paymentIntent } = await stripe.confirmPayment({ elements, redirect: "if_required" });
    if (error || !paymentIntent) {
      setMessage(error?.message ?? "Payment failed");
      return setState("idle");
    }
    const result = await api.confirmCheckout(paymentIntent.id);
    setMessage(result.status === "succeeded" ? "Purchased." : `Payment ${result.status}.`);
    setState("done");
  }

  return (
    <form onSubmit={pay} className="grid gap-3">
      <p className="text-display">{total}</p>
      <LinkAuthenticationElement />
      <PaymentElement options={{ layout: "accordion" }} />
      {message && <p className="text-sm">{message}</p>}
      <button disabled={!stripe || state !== "idle"} className="rule-t rule-b text-display py-2 disabled:text-muted">
        {state === "paying" ? "Paying…" : state === "done" ? "Done" : "Buy now"}
      </button>
    </form>
  );
}
