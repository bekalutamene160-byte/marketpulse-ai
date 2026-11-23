/**
 * Sign-in screen (blueprint FR-001, 14.1 /auth/login).
 *
 * Validation is typed with zod; the SERVER validates independently and its stable
 * error codes drive the messages (uniform UNAUTHORIZED never says which part was
 * wrong). On success the user lands where they were heading (set by the protected
 * route) or on the overview.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button, TextField } from "../../components/ui/Controls";
import { Card } from "../../components/ui/Feedback";
import { authApi, ApiError } from "../../lib/api";
import { SESSION_QUERY_KEY } from "./useSession";

const loginSchema = z.object({
  email: z.email({ message: "Enter a valid email address" }),
  password: z.string().min(1, "Enter your password"),
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [serverMessage, setServerMessage] = useState<string | null>(null);

  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const login = useMutation({
    mutationFn: (values: LoginValues) => authApi.login(values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
      const state = (location.state ?? null) as { from?: unknown } | null;
      const from = state?.from;
      const target = typeof from === "string" && from !== "/login" ? from : "/";
      void navigate(target, { replace: true });
    },
    onError: (error: unknown) => {
      // The server's message is user-safe by contract (blueprint 18.1); unknown
      // failures get a generic line. No detail about email vs password is leaked.
      setServerMessage(
        error instanceof ApiError ? error.message : "Could not sign in. Please try again.",
      );
    },
  });

  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <h1 className="text-xl font-semibold text-ink-50">Sign in</h1>
        <p className="mb-5 mt-1 text-sm text-ink-400">
          Welcome back. Need an account?{" "}
          <Link to="/register" className="text-gold-400 underline-offset-2 hover:underline">
            Create one
          </Link>
        </p>

        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void handleSubmit((values: LoginValues) => {
              login.mutate(values);
            })(event);
          }}
          noValidate
        >
          <TextField
            id="login-email"
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...field("email")}
          />
          <TextField
            id="login-password"
            label="Password"
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...field("password")}
          />

          {serverMessage !== null && (
            <p
              role="alert"
              className="rounded-md border border-status-error/40 px-3 py-2 text-sm text-status-error"
            >
              {serverMessage}
            </p>
          )}

          <Button type="submit" disabled={isSubmitting || login.isPending}>
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
