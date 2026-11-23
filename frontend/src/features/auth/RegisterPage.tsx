/**
 * Registration screen (blueprint FR-001, 14.1 /auth/register).
 *
 * One form creates the user AND their first organization (owner membership +
 * a General workspace on the server side). Password policy is enforced here and
 * re-validated by the server; duplicate email/slug surfaces as 409 CONFLICT.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button, TextField } from "../../components/ui/Controls";
import { Card } from "../../components/ui/Feedback";
import { ApiError, authApi } from "../../lib/api";
import { SESSION_QUERY_KEY } from "./useSession";

const registerSchema = z.object({
  email: z.email({ message: "Enter a valid email address" }),
  password: z
    .string()
    .min(12, "Use at least 12 characters")
    .max(128, "Use at most 128 characters"),
  organization_name: z
    .string()
    .trim()
    .min(1, "Give your organization a name")
    .max(200, "Keep the name under 200 characters"),
});

type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [serverMessage, setServerMessage] = useState<string | null>(null);

  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const register = useMutation({
    mutationFn: (values: RegisterValues) => authApi.register(values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
      void navigate("/", { replace: true });
    },
    onError: (error: unknown) => {
      setServerMessage(
        error instanceof ApiError ? error.message : "Could not create the account. Please try again.",
      );
    },
  });

  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <h1 className="text-xl font-semibold text-ink-50">Create your account</h1>
        <p className="mb-5 mt-1 text-sm text-ink-400">
          Already have one?{" "}
          <Link to="/login" className="text-gold-400 underline-offset-2 hover:underline">
            Sign in
          </Link>
        </p>

        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void handleSubmit((values: RegisterValues) => {
              register.mutate(values);
            })(event);
          }}
          noValidate
        >
          <TextField
            id="register-organization"
            label="Organization name"
            autoComplete="organization"
            error={errors.organization_name?.message}
            {...field("organization_name")}
          />
          <TextField
            id="register-email"
            label="Work email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...field("email")}
          />
          <TextField
            id="register-password"
            label="Password"
            type="password"
            autoComplete="new-password"
            error={errors.password?.message}
            {...field("password")}
          />
          <p className="text-xs text-ink-400">
            At least 12 characters. You will be the owner of your organization and can invite
            your team later.
          </p>

          {serverMessage !== null && (
            <p
              role="alert"
              className="rounded-md border border-status-error/40 px-3 py-2 text-sm text-status-error"
            >
              {serverMessage}
            </p>
          )}

          <Button type="submit" disabled={isSubmitting || register.isPending}>
            {register.isPending ? "Creating account…" : "Create account"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
