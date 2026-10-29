import { CircleAlert } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "@/api/errors";
import { safeNext } from "@/auth/redirect";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

interface LoginForm {
  email: string;
  password: string;
}

const INVALID_CREDENTIALS = "E-mail ou senha inválidos.";
const LOGIN_FAILED = "Não foi possível entrar agora. Verifique a conexão e tente novamente.";
// The reverse proxy limits login attempts per IP and answers 429 past the limit.
const TOO_MANY_ATTEMPTS = "Muitas tentativas. Aguarde um minuto e tente de novo.";

function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return LOGIN_FAILED;
  // 401 (wrong credentials) and 422 (malformed input) get the same generic message on purpose.
  if (error.status === 401 || error.status === 422) return INVALID_CREDENTIALS;
  if (error.status === 429) return TOO_MANY_ATTEMPTS;
  return LOGIN_FAILED;
}

export function LoginPage() {
  useDocumentTitle("Entrar");
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setFocus,
    resetField,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({ defaultValues: { email: "", password: "" } });

  if (status === "authenticated") return <Navigate to={next} replace />;

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setFormError(null);
    try {
      await login(email.trim(), password);
      navigate(next, { replace: true });
    } catch (error) {
      setFormError(loginErrorMessage(error));
      resetField("password");
      setFocus("password");
    }
  });

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-2xl font-bold text-brand-800">Organizador</h1>
        <p className="mb-6 text-slate-600">Entre para organizar a casa.</p>

        <form onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
          {formError && (
            <p role="alert" className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm font-medium text-red-800">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              {formError}
            </p>
          )}
          <TextField
            label="E-mail"
            type="email"
            autoComplete="username"
            inputMode="email"
            autoFocus
            required
            error={errors.email?.message}
            {...register("email", { required: "Informe o e-mail." })}
          />
          <TextField
            label="Senha"
            type="password"
            autoComplete="current-password"
            required
            error={errors.password?.message}
            {...register("password", { required: "Informe a senha." })}
          />
          <Button type="submit" loading={isSubmitting} className="w-full">
            {isSubmitting ? "Entrando..." : "Entrar"}
          </Button>
        </form>
      </div>
    </main>
  );
}
