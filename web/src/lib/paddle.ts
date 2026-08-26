"use client";
/* Paddle.js singleton. The environment is never defaulted silently:
   both env vars must be set or initialization throws a loud error. */
import { initializePaddle, type Paddle } from "@paddle/paddle-js";

let instance: Promise<Paddle | undefined> | null = null;

export function getPaddle(): Promise<Paddle | undefined> {
  if (instance) return instance;
  const env = process.env.NEXT_PUBLIC_PADDLE_ENV;
  const token = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
  if (env !== "sandbox" && env !== "production")
    throw new Error("NEXT_PUBLIC_PADDLE_ENV must be 'sandbox' or 'production' (unset — refusing to guess the Paddle account).");
  if (!token) throw new Error("NEXT_PUBLIC_PADDLE_CLIENT_TOKEN is not set.");
  if (env === "sandbox" && !token.startsWith("test_"))
    throw new Error("Sandbox requires a client-side token prefixed 'test_'.");
  instance = initializePaddle({ environment: env, token });
  return instance;
}
